from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.post("/api/initialize-sample-data")
async def initialize_sample_data():
    # 先放一個 stub，表示功能尚未實作
    raise HTTPException(status_code=501, detail="Sample data initialization not implemented.")

@router.delete("/api/clear-sample-data")
async def clear_sample_data():
    raise HTTPException(status_code=501, detail="Sample data clearing not implemented.")