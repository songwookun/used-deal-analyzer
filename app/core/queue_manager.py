import asyncio


class QueueManager:
    """파이프라인 4단계 큐 관리 (collect → validate → analyze → notify)."""

    def __init__(self, maxsize: int = 100):
        self.collect_queue = asyncio.Queue(maxsize=maxsize)
        self.validate_queue = asyncio.Queue(maxsize=maxsize)
        self.analyze_queue = asyncio.Queue(maxsize=maxsize)
        self.notify_queue = asyncio.Queue(maxsize=maxsize)
        # 매물 파이프라인과 독립된 LLM 헬스체크/검증 채널
        self.llm_ping_queue = asyncio.Queue(maxsize=maxsize)

    def get_status(self) -> dict:
        return {
            "collect": self.collect_queue.qsize(),
            "validate": self.validate_queue.qsize(),
            "analyze": self.analyze_queue.qsize(),
            "notify": self.notify_queue.qsize(),
            "llm_ping": self.llm_ping_queue.qsize(),
        }

    async def shutdown(self):
        # 파이프라인 순서대로 join — 위에서 안 끝나면 아래에 작업이 흘러갈 곳 없음
        await self.collect_queue.join()
        await self.validate_queue.join()
        await self.analyze_queue.join()
        await self.notify_queue.join()
        await self.llm_ping_queue.join()
