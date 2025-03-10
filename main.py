# import the start function from the bot module
from bot import start
import asyncio

# run the bot using asyncio event loop
if __name__ == '__main__':
    asyncio.run(start())
