import aiosqlite  # async work with SQLite
import time  # for timestamps



class DB:
    path: str  # path to database file
    con: aiosqlite.Connection  # connection object

    def __init__(self, path) -> None:
        # Initialize database path
        self.path = path
        self.con = None

    async def bootstrap(self) -> None:
        # Connect to database (open connection)
        if not self.con:
            self.con = await aiosqlite.connect(self.path)

    async def teardown(self) -> None:
        # Close database connection
        await self.con.close()
        
    async def sql(self, sql: str, asdict: bool = False, **params) -> list | None:
        # Execute SQL query and return results
        cursor = await self.con.execute(sql, params)
        rows = await cursor.fetchall()
        
        if asdict:
            # Return list of dicts if asdict=True
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        
        await self.con.commit()  # save changes
        return rows  # return raw rows



    async def set_captcha(self, user_id, code, chat_id=None, kick_at=None, message_id=None):
        # Add or update captcha record for user
        if await self.sql("SELECT 1 FROM captcha WHERE user_id=:user_id AND chat_id=:chat_id", user_id=user_id, chat_id=chat_id):
            await self.sql("UPDATE captcha SET code=:code, kick_at=:kick_at WHERE user_id=:user_id AND chat_id=:chat_id", user_id=user_id, code=code, chat_id=chat_id, kick_at=kick_at)
        else:
            await self.sql("INSERT INTO captcha (user_id, code, chat_id, kick_at, message_id) VALUES (:user_id, :code, :chat_id, :kick_at, :message_id)", user_id=user_id, code=code, chat_id=chat_id, kick_at=kick_at, message_id=message_id)


    async def get_captcha(self, user_id):
        # Get captcha code for user
        return (await self.sql("SELECT code FROM captcha WHERE user_id=:user_id", user_id=user_id))[0][0]
    

    async def iter_users_to_kick(self):
        # Generator: get users who must be kicked now
        now = time.time()
        data = (await self.sql("SELECT chat_id, user_id, message_id FROM captcha where kick_at <= :now", now=now))
        for row in data:
            yield row
    

    async def dont_kick(self, chat_id, user_id):
        # Remove user from captcha table (don't kick)
        await self.sql("DELETE FROM captcha where user_id=:user_id AND chat_id=:chat_id", chat_id=chat_id, user_id=user_id)
    

    async def set_unsolved_captcha(self, user_id):
        # Mark captcha as unsolved for user
        await self.sql("UPDATE users SET captcha = 1 WHERE id=:user_id", user_id=user_id)


    async def set_solved_captcha(self, user_id):
        # Mark captcha as solved for user
        await self.sql("UPDATE users SET captcha = 0 WHERE id=:user_id", user_id=user_id)
