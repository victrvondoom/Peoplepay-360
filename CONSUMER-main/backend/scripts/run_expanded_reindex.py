import asyncio
import sys
sys.path.insert(0, '.')
from app.services.reindex_service import run_reindex
from app.models.domain import Domain

DOMAINS = [Domain.BANKING, Domain.AIRLINES, Domain.HOUSING, Domain.GOVERNMENT]

async def main():
    for d in DOMAINS:
        print(f"=== starting {d.value} ===", flush=True)
        job = await run_reindex(d)
        print(f"=== {d.value} finished: status={job.status} processed={len(job.processed_files)}/{job.total_files} ===", flush=True)

asyncio.run(main())
