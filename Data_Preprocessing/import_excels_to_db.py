#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

sys.path.append(str(Path(__file__).resolve().parents[1] / "privnurse_gemma3n" / "backend"))
from models import Patient, DischargeNote, ConsultationRecord, LabReport, NursingNote  # noqa: E402

# ========= 設定 =========
BASE_DIR = Path("病歷摘要資料")
SUMMARY_DIR = BASE_DIR / "出院摘要"
CONSULT_DIR = BASE_DIR / "會診紀錄"
LAB_DIR = BASE_DIR / "檢驗報告"
NURSING_DIR = BASE_DIR / "護理紀錄"

SUMMARY_PREFIX = "急診出院摘要"
CONSULT_PREFIX = "會診紀錄"
LAB_PREFIX = "檢驗報告"
NURSING_PREFIX = "護理紀錄"

PART_RANGE = range(1, 5)  # part1~part4

IMPORT_USER_ID = int(os.getenv("IMPORT_USER_ID", "1"))

# 你目前 docker compose ports: 3306:3306，所以本機連 127.0.0.1
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://nurse:password@127.0.0.1:3306/inference_db?charset=utf8mb4",
)

# 批次 commit（越大越快，但失敗回滾成本越高）
COMMIT_BATCH = int(os.getenv("COMMIT_BATCH", "2000"))


# ---------------- Logging ----------------
def setup_logger() -> logging.Logger:
    logger = logging.getLogger("import_excels_to_db")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # console only
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(ch)
    logger.propagate = False
    return logger

logger = setup_logger()
# ---------------- DB ----------------
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def db_ping(db: Session) -> None:
    v = db.execute(text("SELECT 1")).scalar()
    logger.info(f"DB connectivity OK (SELECT 1 -> {v})")


# ---------------- Excel utils ----------------
def read_parts(dir_path: Path, prefix: str) -> pd.DataFrame:
    files = [dir_path / f"{prefix}_part{i}.xlsx" for i in PART_RANGE]
    files = [f for f in files if f.exists()]
    if not files:
        logger.warning(f"No files: {dir_path}/{prefix}_part*.xlsx")
        return pd.DataFrame()

    dfs = []
    for f in files:
        logger.info(f"Reading: {f}")
        df = pd.read_excel(f, engine="openpyxl")
        dfs.append(df)

    out = pd.concat(dfs, ignore_index=True)
    logger.info(f"Concatenated {prefix}: total {len(out)} rows")
    return out


def clean_text(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass

    s = str(x)
    s = s.replace("</p>", "").replace("<p>", "").strip()
    return s


def get_mrn_from_row(r: pd.Series) -> Optional[int]:
    """Excel 的『序號』欄位就是 mrn（醫療序號），不是 patient.id。"""
    v = r.get("序號")
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        return int(v)
    except Exception:
        # 有些 Excel 會是 '2000.0' 這種
        try:
            return int(float(v))
        except Exception:
            return None


# ---------------- Patient cache ----------------
class PatientCache:
    """
    mrn -> patient_id cache
    避免每 row 都 query patient
    """

    def __init__(self) -> None:
        self.mrn_to_pid: Dict[int, int] = {}

    def get(self, mrn: int) -> Optional[int]:
        return self.mrn_to_pid.get(mrn)

    def set(self, mrn: int, patient_id: int) -> None:
        self.mrn_to_pid[mrn] = patient_id


def get_or_create_patient(db: Session, mrn: int, cache: PatientCache) -> Patient:
    """
    做法 1：
    - Patient.id：autoincrement
    - Patient.medical_record_no：用 mrn（Excel 序號）當字串
    """
    cached = cache.get(mrn)
    if cached is not None:
        # 只回個 stub 也行，但我們這裡直接查一次避免拿不到物件狀態
        p = db.get(Patient, cached)
        if p is not None:
            return p
        # cache 失效就往下查

    mrn_str = str(mrn)

    p = db.query(Patient).filter(Patient.medical_record_no == mrn_str).first()
    if p:
        cache.set(mrn, p.id)
        return p

    # 建立假想病歷資料（你指定的規格）
    p = Patient(
        medical_record_no=mrn_str,
        name=mrn_str,
        patient_category="NHI General",
        gender="M",
        weight=0,
        department="N/A",
        birthday=date(2000, 1, 1),
        created_by=IMPORT_USER_ID,
    )
    db.add(p)
    db.flush()  # 取得 p.id（避免等到 commit）
    cache.set(mrn, p.id)
    return p


# ---------------- Commit helper ----------------
def maybe_commit(db: Session, inserted: int, label: str, row_i: int) -> None:
    if inserted % COMMIT_BATCH != 0:
        return
    try:
        db.commit()
        logger.info(f"[COMMIT] {label} committed at row={row_i} (batch={COMMIT_BATCH})")
    except Exception as e:
        db.rollback()
        logger.exception(f"[COMMIT-FAIL] {label} at row={row_i}: {e}")
        raise


# ---------------- Importers ----------------
def import_summaries(db: Session, df: pd.DataFrame, cache: PatientCache) -> Tuple[int, int]:
    inserted = 0
    skipped = 0
    if df.empty:
        return inserted, skipped

    for i, r in enumerate(df.itertuples(index=False), start=1):
        # itertuples 比 iterrows 快很多
        r = pd.Series(r._asdict())  # 方便用 r.get
        mrn = get_mrn_from_row(r)
        if mrn is None:
            skipped += 1
            continue

        p = get_or_create_patient(db, mrn, cache)
        pid = p.id

        chief = clean_text(r.get("主訴", ""))
        treatment = clean_text(r.get("治療經過", ""))

        diagnosis_list = []

        def add_diag(category: str, textv) -> None:
            t = clean_text(textv)
            if t:
                diagnosis_list.append(
                    {
                        "category": category,
                        "diagnosis": t,
                        "code": None,
                        "date_diagnosed": None,
                    }
                )

        add_diag("Primary", r.get("主要診斷", ""))
        add_diag("Secondary", r.get("次要診斷", ""))
        add_diag("Past", r.get("過去病史", ""))
        add_diag("Present", r.get("現在病史", ""))

        note = db.query(DischargeNote).filter(DischargeNote.patient_id == pid).first()
        if not note:
            note = DischargeNote(patient_id=pid, created_by=IMPORT_USER_ID)
            db.add(note)

        note.chief_complaint = chief
        note.treatment_course = treatment
        note.diagnosis = diagnosis_list if diagnosis_list else []

        inserted += 1

        # sample log
        if i % 2000 == 0:
            logger.info(
                f"[SAMPLE] summaries row={i} mrn={mrn} patient_id={pid} "
                f"diag={len(diagnosis_list)} chief_len={len(chief)}"
            )

        maybe_commit(db, inserted, "summaries", i)

    return inserted, skipped


def import_consults(db: Session, df: pd.DataFrame, cache: PatientCache) -> Tuple[int, int]:
    inserted = 0
    skipped = 0
    if df.empty:
        return inserted, skipped

    for i, r in enumerate(df.itertuples(index=False), start=1):
        r = pd.Series(r._asdict())
        mrn = get_mrn_from_row(r)
        if mrn is None:
            skipped += 1
            continue

        p = get_or_create_patient(db, mrn, cache)
        pid = p.id

        ts = pd.to_datetime(r.get("回覆時間"), errors="coerce")
        if pd.isna(ts):
            skipped += 1
            continue

        content = clean_text(r.get("回覆內容", ""))
        if not content:
            skipped += 1
            continue

        c = ConsultationRecord(
            patient_id=pid,
            consultation_date=ts.to_pydatetime(),
            original_content=content,
            nurse_confirmation=content,  # 你 XML generator 吃這個
            created_by=IMPORT_USER_ID,
            status="confirmed",
        )
        db.add(c)
        inserted += 1

        if i % 2000 == 0:
            logger.info(
                f"[SAMPLE] consults row={i} mrn={mrn} patient_id={pid} "
                f"ts={ts.to_pydatetime()} content_len={len(content)}"
            )

        maybe_commit(db, inserted, "consults", i)

    return inserted, skipped


def import_labs(db: Session, df: pd.DataFrame, cache: PatientCache) -> Tuple[int, int]:
    inserted = 0
    skipped = 0
    if df.empty:
        return inserted, skipped

    for i, r in enumerate(df.itertuples(index=False), start=1):
        r = pd.Series(r._asdict())
        mrn = get_mrn_from_row(r)
        if mrn is None:
            skipped += 1
            continue

        p = get_or_create_patient(db, mrn, cache)
        pid = p.id

        d = pd.to_datetime(r.get("檢驗日期"), errors="coerce")
        if pd.isna(d):
            skipped += 1
            continue

        test_name = clean_text(r.get("檢驗項目", ""))
        result = clean_text(r.get("檢驗結果", ""))

        if not test_name and not result:
            skipped += 1
            continue

        lab = LabReport(
            patient_id=pid,
            test_name=test_name,
            test_date=d.date(),
            result_value=(result or ""),
            flag="NORMAL",
        )
        db.add(lab)
        inserted += 1

        if i % 2000 == 0:
            logger.info(
                f"[SAMPLE] labs row={i} mrn={mrn} patient_id={pid} date={d.date()} test='{test_name[:30]}'"
            )

        maybe_commit(db, inserted, "labs", i)

    return inserted, skipped


def import_nursing(db: Session, df: pd.DataFrame, cache: PatientCache) -> Tuple[int, int]:
    inserted = 0
    skipped = 0
    if df.empty:
        return inserted, skipped

    for i, r in enumerate(df.itertuples(index=False), start=1):
        r = pd.Series(r._asdict())
        mrn = get_mrn_from_row(r)
        if mrn is None:
            skipped += 1
            continue

        p = get_or_create_patient(db, mrn, cache)
        pid = p.id

        d = str(r.get("日期", "")).strip()
        t = str(r.get("時間", "")).strip()

        # 時間容錯：930 / 09:30 / 930.0
        t = t.replace(":", "")
        if t.endswith(".0"):
            t = t[:-2]
        t = t.zfill(4)

        ts = pd.to_datetime(f"{d}{t}", format="%Y%m%d%H%M", errors="coerce")
        if pd.isna(ts):
            skipped += 1
            continue
        ts_dt = ts.to_pydatetime()

        # VitalSign
        vital_type = clean_text(r.get("類別", ""))
        vital_value = clean_text(r.get("數值紀錄", ""))
        if vital_type and vital_value:
            db.add(
                NursingNote(
                    patient_id=pid,
                    record_time=ts_dt,
                    record_type="VitalSign",
                    content=f"type:{vital_type}|value:{vital_value}",
                    created_by=IMPORT_USER_ID,
                )
            )
            inserted += 1

        # SOAP 欄位
        mapping = [
            ("RECORD_S", "Subjective"),
            ("RECORD_O", "Objective"),
            ("RECORD_I", "Intervention"),
            ("RECORD_E", "Evaluation"),
            ("RECORD_N", "NarrativeNote"),
        ]
        for col, rtype in mapping:
            txt = clean_text(r.get(col, ""))
            if txt:
                db.add(
                    NursingNote(
                        patient_id=pid,
                        record_time=ts_dt,
                        record_type=rtype,
                        content=txt,
                        created_by=IMPORT_USER_ID,
                    )
                )
                inserted += 1

        if i % 2000 == 0:
            logger.info(
                f"[SAMPLE] nursing row={i} mrn={mrn} patient_id={pid} ts={ts_dt.isoformat()}"
            )

        maybe_commit(db, inserted, "nursing", i)

    return inserted, skipped


# ---------------- Main ----------------
def main() -> None:
    logger.info(f"Using DATABASE_URL={DATABASE_URL}")

    df_sum = read_parts(SUMMARY_DIR, SUMMARY_PREFIX)
    df_con = read_parts(CONSULT_DIR, CONSULT_PREFIX)
    df_lab = read_parts(LAB_DIR, LAB_PREFIX)
    df_nur = read_parts(NURSING_DIR, NURSING_PREFIX)

    logger.info(
        f"Loaded rows: summaries={len(df_sum)} consults={len(df_con)} labs={len(df_lab)} nursing={len(df_nur)}"
    )

    db = SessionLocal()
    cache = PatientCache()

    try:
        db_ping(db)

        n1, s1 = import_summaries(db, df_sum, cache)
        db.commit()
        logger.info(f"summaries done: inserted={n1} skipped={s1}")

        n2, s2 = import_consults(db, df_con, cache)
        db.commit()
        logger.info(f"consults done: inserted={n2} skipped={s2}")

        n3, s3 = import_labs(db, df_lab, cache)
        db.commit()
        logger.info(f"labs done: inserted={n3} skipped={s3}")

        n4, s4 = import_nursing(db, df_nur, cache)
        db.commit()
        logger.info(f"nursing done: inserted={n4} skipped={s4}")

        logger.info("[OK] Import finished.")
    except Exception as e:
        db.rollback()
        logger.exception(f"IMPORT FAILED: {e}")
        raise
    finally:
        db.close()
        logger.info("DB session closed.")
        logger.info(f"Log saved to: {LOG_PATH}")


if __name__ == "__main__":
    main()
