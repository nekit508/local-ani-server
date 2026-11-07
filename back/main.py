from contextlib import ExitStack, asynccontextmanager, contextmanager

import click
from fastapi import FastAPI

import db, auth, api
from back.config import settings
from back.terminal_cli import TerminalCLI, Printer


@click.group
def cli(): ...

@cli.command("dih")
@click.option("-s", type=int, default=7)
@click.pass_obj
def dih(obj: Printer, s: int):
    obj.print(f"dih is {s}cm long")

@contextmanager
def terminal_cli():
    _ = TerminalCLI(settings.ADMIN_SOCKETS, cli)
    _.start()
    yield
    _.stop()


@asynccontextmanager
async def lifespan(app):
    # noinspection PyAbstractClass
    with ExitStack() as stack:
        stack.enter_context(db.lifespan(app))
        stack.enter_context(terminal_cli())
        yield

application = FastAPI(title="backend", lifespan=lifespan)

application.include_router(auth.router)
application.include_router(api.router)