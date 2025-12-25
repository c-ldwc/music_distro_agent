from random import random
from typing import Any, Callable
from time import sleep


def retry[T](
    method: Callable[[], T], args: dict[str, Any], retries: int = 3
) -> T | None:
    """Retries the method function retries many times with a random wait on [.5, 1.5)

    Args:
        method: The function to retry
        args: The function's arguments
        retries: The number of retries

    Returns:
        The output of the method, or None if all retries failed
    """
    tries = 0
    while tries < 3:
        try:
            return method(**args)
        except Exception as err:
            tries += 1
            sleep(random() + 0.5)
            if tries == 3:
                raise err
