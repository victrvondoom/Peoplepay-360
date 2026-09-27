import asyncio
import sys
sys.path.insert(0, '.')
from app.services.reindex_service import run_reindex
from app.models.domain import Domain

async def main():
    print("=== starting healthcare ===", flush=True)
    job = await run_reindex(Domain.HEALTHCARE)
    print(f"=== healthcare finished: status={job.status} processed={len(job.processed_files)}/{job.total_files} ===", flush=True)

asyncio.run(main())
