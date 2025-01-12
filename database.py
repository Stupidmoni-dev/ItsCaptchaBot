import aiosqlite
import time

# сори, но тут уже без коментов

class DB:
    path: str
    con: aiosqlite.Connection

    def __init__(self, path) -> None:
        self.path = path
        self.con = None

    async def bootstrap(self) -> None:
        if not self.con:
            self.con = await aiosqlite.connect(self.path)

    async def teardown(self) -> None:
        await self.con.close()
        
    async def sql(self, sql: str, asdict: bool = False, **params) -> list | None:
        cursor = await self.con.execute(sql, params)
        rows = await cursor.fetchall()
        
        if asdict:
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        
        await self.con.commit()
        return rows




    async def set_captcha(self, user_id, code, chat_id=None, kick_at=None, message_id=None):
        if await self.sql("SELECT 1 FROM captcha WHERE user_id=:user_id AND chat_id=:chat_id", user_id=user_id, chat_id=chat_id):
            await self.sql("UPDATE captcha SET code=:code, kick_at=:kick_at WHERE user_id=:user_id AND chat_id=:chat_id", user_id=user_id, code=code, chat_id=chat_id, kick_at=kick_at)
        else:
            await self.sql("INSERT INTO captcha (user_id, code, chat_id, kick_at, message_id) VALUES (:user_id, :code, :chat_id, :kick_at, :message_id)", user_id=user_id, code=code, chat_id=chat_id, kick_at=kick_at, message_id=message_id)


    async def get_captcha(self, user_id):
        return (await self.sql("SELECT code FROM captcha WHERE user_id=:user_id", user_id=user_id))[0][0]
    

    async def iter_users_to_kick(self):
        now = time.time()
        data = (await self.sql("SELECT chat_id, user_id, message_id FROM captcha where kick_at <= :now", now=now))
        for row in data:
            yield row
    

    async def dont_kick(self, chat_id, user_id):
        await self.sql("DELETE FROM captcha where user_id=:user_id AND chat_id=:chat_id", chat_id=chat_id, user_id=user_id)
    

    async def set_unsolved_captcha(self, user_id):
        await self.sql("UPDATE users SET captcha = 1 WHERE id=:user_id", user_id=user_id)


    async def set_solved_captcha(self, user_id):
        await self.sql("UPDATE users SET captcha = 0 WHERE id=:user_id", user_id=user_id)
