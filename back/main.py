from contextlib import ExitStack, asynccontextmanager

import click
from fastapi import FastAPI

import back.databases
from back.config import settings
from back.controllers import search, api, auth, videos
from back.services.users import create_new_user_
from back.lib.terminal_cli import TerminalCLI


@click.group()
def cli(): ...


@cli.group()
def user(): ...


@user.command("create")
@click.argument("username", type=str)
@click.argument("password", type=str)
def create(username: str, password: str):
    user = create_new_user_(username, password)
    if user is None:
        print("User with same username already exists")
    else:
        print(f"Created user {user.login}:{user.id}")


# noinspection PyUnusedLocal
@asynccontextmanager
async def lifespan(app):
    # noinspection PyAbstractClass
    with ExitStack() as stack:
        stack.enter_context(back.databases.lifespan())
        stack.enter_context(TerminalCLI(settings.ADMIN_SOCKETS, cli).lifespan)
        yield

application = FastAPI(title="backend", lifespan=lifespan)

application.include_router(auth.router)
application.include_router(api.router)
application.include_router(search.router)
application.include_router(videos.router)