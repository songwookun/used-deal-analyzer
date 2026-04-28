"""
LLM 헬스체크/검증 워커.

- llm_ping_queue 만 바라봄 (매물 파이프라인과 무관)
- 큐 메시지 형식: {"prompt": str, "force_fallback": bool (optional)}
- 결과는 콘솔 출력 + ExternalClient가 api_req_res_logs에 자동 기록
"""
from datetime import date

from app.core.queue_manager import QueueManager
from app.services.llm_client import LLMClient


async def llm_ping_worker(queue_mgr: QueueManager, llm_client: LLMClient) -> None:
    """llm_ping_queue 소비 → LLMClient.analyze() 호출 → 결과 콘솔 출력."""
    while True:
        msg = await queue_mgr.llm_ping_queue.get()
        try:
            prompt = msg["prompt"]
            if msg.get("force_fallback"):
                # 메모리 플래그 강제 set → 다음 analyze() 호출이 바로 fallback으로 감
                llm_client._primary_quota_blocked_date = date.today()
                print("[llm_ping] force_fallback=true — primary 차단 플래그 강제 set")

            result = await llm_client.analyze(prompt)
            print(f"[llm_ping] OK prompt={prompt!r} result={result!r}")

        except Exception as e:
            print(f"[llm_ping] FAILED msg={msg!r} error={e!r}")
        finally:
            queue_mgr.llm_ping_queue.task_done()
