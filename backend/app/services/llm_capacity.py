import asyncio

llm_semaphore = asyncio.Semaphore(20)
