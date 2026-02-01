from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor

from academy.agent import action
from academy.agent import Agent
from academy.exchange.cloud.client import HttpExchangeFactory
from academy.handle import Handle
from academy.logging import init_logging
from academy.manager import Manager
from globus_compute_sdk import Executor as GCExecutor

EXCHANGE_ADDRESS = 'https://exchange.academy-agents.org'
logger = logging.getLogger(__name__)


class Coordinator(Agent):
    def __init__(
        self,
        lowerer: Handle[Lowerer],
        reverser: Handle[Reverser],
    ) -> None:
        super().__init__()
        self.lowerer = lowerer
        self.reverser = reverser

    @action
    async def process(self, text: str) -> str:
        text = await self.lowerer.lower(text)
        text = await self.reverser.reverse(text)
        return text


class Lowerer(Agent):
    @action
    async def lower(self, text: str) -> str:
        return text.lower()


class Reverser(Agent):
    @action
    async def reverse(self, text: str) -> str:
        return text[::-1]


async def main() -> int:
    init_logging(logging.INFO)

    if 'ACADEMY_ENDPOINT' in os.environ:
        executor = GCExecutor(os.environ['ACADEMY_ENDPOINT'])
        remote = True
    else:
        mp_context = multiprocessing.get_context('spawn')
        executor = ProcessPoolExecutor(
            max_workers=3,
            initializer=init_logging,
            mp_context=mp_context,
        )
        remote = False

    async with await Manager.from_exchange_factory(
        factory=HttpExchangeFactory(
            EXCHANGE_ADDRESS,
            auth_method='globus',
        ),
        # Agents are run by the manager in the processes of this
        # process pool executor.
        executors=executor,
    ) as manager:
        # Launch each of the three agents types. The returned type is
        # a handle to that agent used to invoke actions.
        lowerer = await manager.launch(Lowerer)
        reverser = await manager.launch(Reverser)
        coordinator = await manager.launch(
            Coordinator,
            args=(lowerer, reverser),
        )

        text = 'DEADBEEF'
        expected = 'feebdaed'

        logger.info(
            'Invoking process("%s") on %s',
            text,
            coordinator.agent_id,
        )
        result = await coordinator.process(text)
        
        status = "PASS" if result == expected else "FAIL"
        mode = "Remote" if 'ACADEMY_ENDPOINT' in os.environ else "Local"
        exit_code = 0 if result == expected else 1
        
        with open('test_result.txt', 'w') as f:
            f.write('='*60 + '\n')
            f.write(f'Mode:     {mode}\n')
            f.write(f'Input:    {text}\n')
            f.write(f'Expected: {expected}\n')
            f.write(f'Result:   {result}\n')
            f.write(f'Status:   {status}\n')
            f.write('='*60 + '\n')
        
        logger.info('Received result: "%s"', result)
        
        if exit_code != 0:
            return exit_code

    # Upon exit, the Manager context will instruct each agent to shutdown,
    # closing their respective handles, and shutting down the executors.

    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
