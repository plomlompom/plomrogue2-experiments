Preliminary study on mechanisms useful for a new PlomRogue engine
=================================================================

The old PlomRogue engine in its mechanisms feels quite questionable to me now.
I have some ideas for a new variant, but I must get acquainted with some
relevant mechanics and their Python3 implementations first. So this code is just
some playing around with these.

A new PlomRogue engine should have:

* server-client communication via sockets, on top of some internet protocol
* the server should be capable of parallel computation
* maybe use a different library for console interfaces than ncurses – how about
  *urwid*?

To play around with these mechanics, I create two executables to be run in
dialogue:

* `./client.py`
* `./server.py`

See `./requirements.txt` for the dependencies.
