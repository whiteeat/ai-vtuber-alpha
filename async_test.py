import time
import asyncio

async def my_task(t):
    await asyncio.sleep(0)
    time.sleep(t)

# await asyncio.sleep(0)会让协程进入让权态
async def main():
    print("Start")
    task = asyncio.create_task(coro())
    await asyncio.sleep(0)
    print("Waiting...")
    await asyncio.sleep(0)
    print("Sleep finishes")
    await task
    print("Exit")

async def coro():
    print("The task begins")
    await asyncio.sleep(4)
    print("The task ends")

if __name__ == '__main__':
    asyncio.run(main())


async def main():
    print("Start")
    task = asyncio.create_task(coro())
    await asyncio.sleep(0)
    print("Waiting...")
    await my_task(4)
    print("Sleep finishes")
    await task
    print("Exit")

async def coro():
    print("The task begins")
    await my_task(8)
    print("The task ends")

if __name__ == '__main__':
    asyncio.run(main())