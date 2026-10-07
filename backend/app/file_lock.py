"""The same exclusive file-lock contract on Unix and Windows."""
import os
import time

if os.name != 'nt':
    from fcntl import flock, LOCK_EX, LOCK_UN
else:
    import errno
    import msvcrt
    LOCK_EX = 2
    LOCK_UN = 8

    def flock(fd, operation):
        if os.fstat(fd).st_size == 0:
            os.write(fd, b'\0')
        os.lseek(fd, 0, os.SEEK_SET)
        if operation == LOCK_UN:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            return
        if operation != LOCK_EX:
            raise ValueError('Only exclusive lock/unlock is supported')
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                time.sleep(0.1)
