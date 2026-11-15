def pause(world, reason):
    if reason not in {"manual", "dialogue", "offline", "idle"}:
        raise ValueError("invalid pause reason")
    world.pause_reasons.add(reason)


def resume(world, reason):
    world.pause_reasons.discard(reason)


def advance(world, ticks):
    if world.pause_reasons:
        raise ValueError("paused")
    if type(ticks) is not int or ticks < 0 or world.tick is None:
        raise ValueError("invalid tick")
    world.tick += ticks
