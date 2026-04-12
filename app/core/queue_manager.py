"""
    파이프라인 큐 4개를 관리하는 클래스입니다.

    [요구사항]

    1. __init__(self, maxsize: int = 100)
       - asyncio.Queue 4개를 생성해주세요
       - collect_queue   (Queue-1: 수집된 매물 대기)
       - validate_queue  (Queue-2: 검증 대기)
       - analyze_queue   (Queue-3: LLM 분석 대기)
       - notify_queue    (Queue-4: 알림 전송 대기)
       - 각 큐에 maxsize를 적용해주세요

    2. get_status(self) -> dict
       - 각 큐의 현재 대기 건수(qsize)를 dict로 리턴해주세요
       - 예: {"collect": 3, "validate": 0, "analyze": 1, "notify": 5}
       - 이건 나중에 /health API에서 큐 상태 모니터링할 때 씁니다

    3. async shutdown(self)
       - 4개 큐가 전부 비워질 때까지 대기하는 메서드입니다
       - asyncio.Queue의 join()을 사용하세요
       - 순서: collect → validate → analyze → notify (파이프라인 순서대로)
       - 이건 앱 종료 시 처리 중인 작업이 유실되지 않게 하려는 겁니다

"""

import asyncio

class QueueManager:

    def __init__(self, maxsize: int = 100):
        self.collect_queue = asyncio.Queue(maxsize=maxsize)
        self.validate_queue = asyncio.Queue(maxsize=maxsize)
        self.analyze_queue = asyncio.Queue(maxsize=maxsize)
        self.notify_queue = asyncio.Queue(maxsize=maxsize)
    """

    """ 
    def get_status(self) -> dict:
        return{
            "collect": self.collect_queue.qsize(),
            "validate": self.validate_queue.qsize(),
            "analyze": self.analyze_queue.qsize(),
            "notify": self.notify_queue.qsize()
        }

    async def shutdown(self):
        await self.collect_queue.join()
        await self.validate_queue.join()
        await self.analyze_queue.join()
        await self.notify_queue.join()
