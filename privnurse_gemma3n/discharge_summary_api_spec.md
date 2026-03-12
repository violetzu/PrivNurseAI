# 出院摘要 API 規格書

**版本**: 1.0
**服務**: 出院摘要生成與驗證
**Base URL**: `http://<host>:<port>`
**認證**: Bearer Token（`Authorization: Bearer <token>`）

---

## 目錄

1. [生成出院摘要](#1-生成出院摘要)
2. [驗證出院摘要](#2-驗證出院摘要)
3. [模型輸入 XML 結構詳解](#3-模型輸入-xml-結構詳解)
4. [資料欄位定義](#4-資料欄位定義)
5. [錯誤碼](#5-錯誤碼)

---

## 1. 生成出院摘要

### `POST /gen-discharge-summary`

接收病患結構化資料，送入 LLM 模型，串流回傳生成的出院治療摘要。

---

### 1.1 Request Body

```json
{
  "caseno": "string",
  "hhisnum": "string",
  "deviceId": "string",
  "hnursta": "string",
  "hbed": "string",
  "summary": {
    "primary_diagnosis": "string",
    "secondary_diagnosis": "string",
    "past_medical_history": "string",
    "chief_complaint": "string",
    "present_illness": "string"
  },
  "nursing_events": [
    {
      "timestamp": "YYYY-MM-DD HH:MM:SS",
      "type": "VitalSign | Subjective | Objective | Intervention | Evaluation | NarrativeNote",
      "content": "string",
      "vital_type": "string (僅 type=VitalSign 時使用)"
    }
  ],
  "lab_reports": [
    {
      "date": "YYYY-MM-DD",
      "items": [
        {
          "name": "string",
          "value": "string",
          "unit": "string",
          "flag": "NORMAL | HIGH | LOW | CRITICAL"
        }
      ]
    }
  ],
  "consultations": [
    {
      "timestamp": "YYYY-MM-DD HH:MM:SS",
      "nurse_confirmation": "string"
    }
  ]
}
```

#### 欄位說明

| 欄位 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `caseno` | string | **是** | 就診號（8 碼），如 `00000003` |
| `hhisnum` | string | **是** | HIS 系統內部病歷識別碼，如 `000000000A` |
| `deviceId` | string | **是** | 裝置代碼（HIS 傳入或固定設定），如 `ER-1` |
| `hnursta` | string | 否 | 護理站代碼（HIS 站點代號），如 `ER` |
| `hbed` | string | 否 | 床位號碼 ( HIS )，如 `123` |
| `summary.primary_diagnosis` | string | 否 | 主要診斷，含 ICD 碼（如：`高血壓 (I10)`） |
| `summary.secondary_diagnosis` | string | 否 | 次要診斷，多項以 `;` 分隔 |
| `summary.past_medical_history` | string | 否 | 過去病史，多項以 `;` 分隔 |
| `summary.chief_complaint` | string | 否 | 主訴 |
| `summary.present_illness` | string | 否 | 現病史 |
| `nursing_events` | array | 否 | 護理記錄事件列表（建議提供最近 20 筆） |
| `nursing_events[].timestamp` | string | 是 | 記錄時間，格式 `YYYY-MM-DD HH:MM:SS` |
| `nursing_events[].type` | string | 是 | 記錄類型（見下方類型表） |
| `nursing_events[].content` | string | 是 | 記錄內容 |
| `nursing_events[].vital_type` | string | 條件 | 生理量測名稱（如 `BP`、`HR`），僅 `type=VitalSign` 時使用 |
| `lab_reports` | array | 否 | 檢驗報告，依日期分組（建議提供近 365 天） |
| `lab_reports[].date` | string | 是 | 檢驗日期，格式 `YYYY-MM-DD` |
| `lab_reports[].items` | array | 是 | 該日期的檢驗項目列表 |
| `lab_reports[].items[].name` | string | 是 | 檢驗項目名稱（如 `WBC`、`Hemoglobin`） |
| `lab_reports[].items[].value` | string | 是 | 檢驗結果數值 |
| `lab_reports[].items[].unit` | string | 否 | 單位（如 `K/uL`、`g/dL`） |
| `lab_reports[].items[].flag` | string | 否 | HIS 傳入的異常旗標（`NORMAL`、`HIGH`、`LOW`、`CRITICAL`），若無則 `NULL` |
| `consultations` | array | 否 | 會診記錄列表（建議提供最近 10 筆） |
| `consultations[].timestamp` | string | 是 | 會診時間，格式 `YYYY-MM-DD HH:MM:SS` |
| `consultations[].nurse_confirmation` | string | 是 | 護理師確認後的會診內容（空字串則略過此筆） |

#### `nursing_events[].type` 類型定義

| 值 | 說明 |
|----|------|
| `VitalSign` | 生命徵象（搭配 `vital_type` 和 `content` 作為數值） |
| `Subjective` | SOAP — 主觀資料（病人主訴） |
| `Objective` | SOAP — 客觀資料（護理師觀察） |
| `Intervention` | SOAP — 護理介入措施 |
| `Evaluation` | SOAP — 護理評值 |
| `NarrativeNote` | 敘述型護理記錄 |

---

### 1.2 送入模型的 XML Prompt

後端將 Request Body 轉換為以下 XML 結構後送入 LLM：

```xml
<PatientEncounter summary_length_style="short|medium|long">
    <Summary>
        <CaseNo>00000003</CaseNo>
        <HhisNum>000000000A</HhisNum>
        <NursingStation>ER</NursingStation>
        <Bed>123</Bed>
        <PrimaryDiagnosis>高血壓 (I10)</PrimaryDiagnosis>
        <SecondaryDiagnosis>第二型糖尿病 (E11)</SecondaryDiagnosis>
        <PastMedicalHistory>冠狀動脈疾病</PastMedicalHistory>
        <ChiefComplaint>頭暈、胸悶</ChiefComplaint>
        <PresentIllness>病人因持續頭暈三天入院</PresentIllness>
    </Summary>
    <ChronologicalEvents>
        <!-- 生命徵象 -->
        <NursingEvent timestamp="2024-01-01 08:00:00">
            <VitalSign type="BP" value="158/95 mmHg" />
        </NursingEvent>
        <!-- SOAP 護理記錄 -->
        <NursingEvent timestamp="2024-01-01 09:30:00">
            <SOAPNote>
                <Subjective>病人表示頭痛改善</Subjective>
            </SOAPNote>
        </NursingEvent>
        <NursingEvent timestamp="2024-01-02 14:00:00">
            <SOAPNote>
                <Intervention>給予降壓藥物 Amlodipine 5mg po qd</Intervention>
            </SOAPNote>
        </NursingEvent>
        <!-- 檢驗報告（按日期分組） -->
        <LabReportGroup date="2024-01-01">
            <Item name="WBC">10.5 K/uL (HIGH)</Item>
            <Item name="Hemoglobin">12.8 g/dL</Item>
            <Item name="Creatinine">1.2 mg/dL</Item>
        </LabReportGroup>
        <!-- 會診記錄 -->
        <Consultation timestamp="2024-01-02 10:00:00">
            <Content>
            心臟科會診：建議調整降壓藥物，加強血壓監控
            </Content>
        </Consultation>
    </ChronologicalEvents>
</PatientEncounter>
```

**`summary_length_style` 自動計算規則**（依總內容字元數）：

| 值 | 條件 |
|----|------|
| `short` | 總字元數 < 1,200 |
| `medium` | 1,200 ≤ 總字元數 < 2,100 |
| `long` | 總字元數 ≥ 2,100 |

---

### 1.3 Response（串流）

- **Content-Type**: `application/x-ndjson`
- **格式**: 每行一個 JSON 物件（NDJSON），`predictDatas` 陣列包裝

**串流進行中（每行）**：
```json
{
  "key": "f64a26ca79c24f6bb76e3379c30d682a",
  "predictDatas": [
    {
      "deviceId": "ER-1",
      "hnursta": "ER",
      "hbed": "123",
      "caseno": "00000003",
      "hhisnum": "000000000A",
      "response": "病人因高血壓急性惡化",
      "done": false
    }
  ]
}
```

**串流結束（最後一行）**：
```json
{
  "key": "f64a26ca79c24f6bb76e3379c30d682a",
  "predictDatas": [
    {
      "deviceId": "ER-1",
      "hnursta": "ER",
      "hbed": "123",
      "caseno": "00000003",
      "hhisnum": "000000000A",
      "predict_local": "2024-01-01 08:00:00",
      "result": "病人因高血壓急性惡化，入院後給予 Amlodipine 5mg...",
      "done": true,
      "type": "NULL"
    }
  ]
}
```

#### Response 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `key` | string | HIS 提供的授權金鑰，如 `f64a26ca79c24f6bb76e3379c30d682a` |
| `predictDatas` | array | 結果陣列（固定 1 筆） |
| `predictDatas[].deviceId` | string | 裝置代碼（原樣回傳） |
| `predictDatas[].hnursta` | string | 護理站代碼（原樣回傳） |
| `predictDatas[].hbed` | string | 床位號碼（原樣回傳） |
| `predictDatas[].caseno` | string | 就診號（原樣回傳） |
| `predictDatas[].hhisnum` | string | HIS 病歷識別碼（原樣回傳） |
| `predictDatas[].response` | string | 串流片段文字（僅 `done: false` 時） |
| `predictDatas[].result` | string | 完整生成摘要（僅 `done: true` 時） |
| `predictDatas[].predict_local` | string | 生成完成時間，格式 `YYYY-MM-DD HH:MM:SS`（僅 `done: true` 時） |
| `predictDatas[].done` | boolean | `false` = 串流進行中；`true` = 串流結束 |
| `predictDatas[].type` | string | AI 模組名稱（固定值），目前為 `"NULL"`（尚未確定）（僅 `done: true` 時） |

**完整摘要** = 所有 `done: false` 的 `response` 欄位串接，或直接取 `done: true` 的 `result`。

---

## 2. 驗證出院摘要

### `POST /gen-discharge-validation`

將原始病患資料（同上 XML 結構）與護理師撰寫的出院摘要文字送入驗證模型，回傳摘要中有原始資料依據的關鍵詞列表，供前端高亮標記使用。

---

### 2.1 Request Body

欄位結構與 [1.1 Request Body](#11-request-body) 相同，額外新增以下欄位：

```json
{
  "...": "（同 1.1）",
  "treatment_course": "string"
}
```

| 欄位 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `caseno` / `hhisnum` / `deviceId` / `hnursta` / `hbed` / `summary` / `nursing_events` / `lab_reports` / `consultations` | — | 同 1.1 | 詳見 [1.1 欄位說明](#11-request-body) |
| `treatment_course` | string | **是** | 護理師撰寫或由生成 API 產出的出院治療摘要全文 |

---

### 2.2 送入模型的 Prompt

```
<PatientEncounter summary_length_style="...">
    （與生成 API 相同的 XML 結構）
</PatientEncounter>
<Discharge_Summary>
病人因高血壓急性惡化入院，入院後給予 Amlodipine 5mg 調整治療方案...
（完整出院摘要文字）
</Discharge_Summary>
```

模型根據兩段內容對照，輸出有資料支撐的關鍵詞，期望回傳格式：
```json
{"result": ["高血壓", "Amlodipine 5mg", "血壓監控", "心臟科會診"]}
```

---

### 2.3 Response

- **Content-Type**: `application/json`

```json
{
  "key": "f64a26ca79c24f6bb76e3379c30d682a",
  "predictDatas": [
    {
      "deviceId": "ER-1",
      "hnursta": "ER",
      "hbed": "123",
      "caseno": "00000003",
      "hhisnum": "000000000A",
      "predict_local": "2024-01-01 14:20:32",
      "result": ["高血壓急性惡化", "Amlodipine 5mg", "心臟科會診", "血壓監控", "WBC 偏高"],
      "type": "NULL"
    }
  ]
}
```

#### Response 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `key` | string | HIS 提供的授權金鑰，如 `f64a26ca79c24f6bb76e3379c30d682a` |
| `predictDatas` | array | 結果陣列（固定 1 筆） |
| `predictDatas[].deviceId` | string | 裝置代碼（原樣回傳） |
| `predictDatas[].hnursta` | string | 護理站代碼（原樣回傳） |
| `predictDatas[].hbed` | string | 床位號碼（原樣回傳） |
| `predictDatas[].caseno` | string | 就診號（原樣回傳） |
| `predictDatas[].hhisnum` | string | HIS 病歷識別碼（原樣回傳） |
| `predictDatas[].predict_local` | string | 驗證完成時間，格式 `YYYY-MM-DD HH:MM:SS` |
| `predictDatas[].result` | string[] | 出院摘要中有原始病歷資料支撐的詞彙/短句列表，供前端高亮標記 |
| `predictDatas[].type` | string | AI 模組名稱（固定值），目前為 `"NULL"`（尚未確定） |

---

## 3. 模型輸入 XML 結構詳解

### 完整 XML 範例

```xml
<PatientEncounter summary_length_style="long">
    <Summary>
        <CaseNo>00000003</CaseNo>
        <HhisNum>000000000A</HhisNum>
        <PrimaryDiagnosis>高血壓 (I10); 急性心衰竭 (I50.9)</PrimaryDiagnosis>
        <SecondaryDiagnosis>第二型糖尿病 (E11); 慢性腎病 Stage 3 (N18.3)</SecondaryDiagnosis>
        <PastMedicalHistory>冠狀動脈疾病; 心房顫動</PastMedicalHistory>
        <ChiefComplaint>呼吸困難、下肢水腫三天</ChiefComplaint>
        <PresentIllness>病人因漸進性呼吸困難及雙下肢水腫三天就醫</PresentIllness>
    </Summary>
    <ChronologicalEvents>
        <NursingEvent timestamp="2024-01-10 08:00:00">
            <VitalSign type="BP" value="168/102 mmHg" />
        </NursingEvent>
        <NursingEvent timestamp="2024-01-10 08:00:00">
            <VitalSign type="SpO2" value="91%" />
        </NursingEvent>
        <NursingEvent timestamp="2024-01-10 09:00:00">
            <SOAPNote>
                <Subjective>病人表示喘不過氣，躺平時更嚴重</Subjective>
            </SOAPNote>
        </NursingEvent>
        <NursingEvent timestamp="2024-01-10 10:30:00">
            <SOAPNote>
                <Intervention>給予氧氣治療 O2 4L/min via nasal cannula，SpO2 升至 96%</Intervention>
            </SOAPNote>
        </NursingEvent>
        <LabReportGroup date="2024-01-10">
            <Item name="BNP">1250 pg/mL (HIGH)</Item>
            <Item name="Creatinine">1.8 mg/dL (HIGH)</Item>
            <Item name="Na">132 mEq/L (LOW)</Item>
        </LabReportGroup>
        <NursingEvent timestamp="2024-01-11 14:00:00">
            <SOAPNote>
                <Evaluation>病人水腫改善，SpO2 維持 97%，呼吸困難緩解</Evaluation>
            </SOAPNote>
        </NursingEvent>
        <Consultation timestamp="2024-01-11 11:00:00">
            <Content>
            心臟科會診：確認急性心衰竭診斷，建議給予 Furosemide 40mg IV，限水 1500ml/day，監測每日體重及尿量
            </Content>
        </Consultation>
        <NursingEvent timestamp="2024-01-12 08:00:00">
            <SOAPNote>
                <NarrativeNote>病人今日體重下降 1.5kg，下肢水腫明顯改善，準備出院</NarrativeNote>
            </SOAPNote>
        </NursingEvent>
    </ChronologicalEvents>
</PatientEncounter>
```

---

## 4. 資料欄位定義

### Diagnosis 物件（diagnosis array 中的元素）

```json
{
  "category": "Primary | Secondary | Past | Current",
  "diagnosis": "string",
  "code": "string（ICD-10 碼，選填）"
}
```

多筆診斷組合後以 `; ` 分隔串接為 XML 欄位值。

### NursingEvent type 對應關係

| 前端/DB 值 | XML 標籤 | 說明 |
|-----------|---------|------|
| `VitalSign` | `<VitalSign type="" value="">` | 生命徵象 |
| `Subjective` | `<SOAPNote><Subjective>` | 主觀資料 |
| `Objective` | `<SOAPNote><Objective>` | 客觀資料 |
| `Intervention` | `<SOAPNote><Intervention>` | 護理介入 |
| `Evaluation` | `<SOAPNote><Evaluation>` | 護理評值 |
| `NarrativeNote` | `<SOAPNote><NarrativeNote>` | 敘述型記錄 |

### LabReport flag 定義

由 HIS 傳入，若無則帶 `NULL`。

| 值 | 說明 | XML 呈現方式 |
|----|------|------------|
| `NULL` | 未提供 | 不附加旗標 |
| `NORMAL` | 正常範圍 | 不附加旗標 |
| `HIGH` | 高於正常值 | 數值後加 `(HIGH)` |
| `LOW` | 低於正常值 | 數值後加 `(LOW)` |
| `CRITICAL` | 危急值 | 數值後加 `(CRITICAL)` |

---

## 5. 錯誤碼

| HTTP Status | 情境 | Response 範例 |
|-------------|------|--------------|
| `400` | 未設定啟用中的模型 | `{"detail": "No active discharge note summary model configured"}` |
| `401` | 未提供或無效的 Bearer Token | `{"detail": "Unauthorized"}` |
| `404` | 病患不存在 | `{"detail": "Patient not found"}` |
| `500` | 資料準備失敗 / Ollama 服務異常 | `{"detail": "Error preparing patient data: ..."}` |

---

## 附錄：完整請求範例

### 生成出院摘要 Request

```bash
curl -X POST "http://localhost:8000/gen-discharge-summary" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "caseno": "00000003",
    "hhisnum": "000000000A",
    "deviceId": "ER-1",
    "hnursta": "ER",
    "hbed": "123",
    "summary": {
      "primary_diagnosis": "高血壓 (I10)",
      "secondary_diagnosis": "第二型糖尿病 (E11)",
      "past_medical_history": "冠狀動脈疾病",
      "chief_complaint": "頭暈、胸悶",
      "present_illness": "病人因持續頭暈三天入院"
    },
    "nursing_events": [
      {
        "timestamp": "2024-01-10 08:00:00",
        "type": "VitalSign",
        "vital_type": "BP",
        "content": "158/95 mmHg"
      },
      {
        "timestamp": "2024-01-10 09:30:00",
        "type": "Intervention",
        "content": "給予 Amlodipine 5mg po qd"
      }
    ],
    "lab_reports": [
      {
        "date": "2024-01-10",
        "items": [
          { "name": "WBC", "value": "10.5", "unit": "K/uL", "flag": "HIGH" },
          { "name": "Hemoglobin", "value": "12.8", "unit": "g/dL", "flag": "NORMAL" }
        ]
      }
    ],
    "consultations": [
      {
        "timestamp": "2024-01-11 10:00:00",
        "nurse_confirmation": "心臟科建議調整降壓藥物"
      }
    ]
  }'
```

### 驗證出院摘要 Request

```bash
curl -X POST "http://localhost:8000/gen-discharge-validation" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "caseno": "00000003",
    "hhisnum": "000000000A",
    "deviceId": "ER-1",
    "hnursta": "ER",
    "hbed": "123",
    "summary": { ... },
    "nursing_events": [ ... ],
    "lab_reports": [ ... ],
    "consultations": [ ... ],
    "treatment_course": "病人因高血壓急性惡化合併頭暈症狀入院，入院後給予 Amlodipine 5mg 調整治療，血壓逐漸控制至目標值，症狀改善後出院。"
  }'
```
