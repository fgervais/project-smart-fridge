import code, traceback, signal


teardown = None

def debug(sig, frame):
    if teardown is not None:
        teardown()

    """Interrupt running process, and provide a python prompt for
    interactive debugging."""
    d={'_frame':frame}         # Allow access to frame object.
    d.update(frame.f_globals)  # Unless shadowed by global
    d.update(frame.f_locals)

    i = code.InteractiveConsole(d)
    message  = "Signal received : entering python shell.\nTraceback:\n"
    message += ''.join(traceback.format_stack(frame))
    i.interact(message)

def teardown_function(function):
    global teardown

    teardown = function

def register_debug_hook():
    signal.signal(signal.SIGUSR1, debug)  # Register handler
