#
# logdbgview.py
#
# Author: Ken McFadden
#
# Based on code found at http://timgolden.me.uk/python/win32_how_do_i/capture-OutputDebugString.html
# by Tim Golden and Dan Brotherston
#
# This code was written to run with Python version 3.3.
#
# LogDbgView captures Windows Win32 OutputDebugString messages to a log file.
# As such it is a Python class that acts much like the Windows DebugView utility.
#
# An example use for this functionality could be to run several windows
# applications that generate debug output with the OutputDebugString and capture
# a debug log file for each.
#
# Using LogDbgView, you can automate the collection of debug log files by
# writing a Python script that loops over a list of applications to run and just
# prior to executing the application call LogDbgView.makeLogDbgView to capture
# the debug information to a log file.
#
# The manual alternative to this would be to use the DebugView utility to do
# the following for each application you run:
#     start DebugView
#     start the windows application that will call OutputDebugString
#     wait for the application to finish
#     save the debug messages to a log file from DebugView using File->SaveAs
#     exit DebugView
#
# Keep in mind that LogDbgView and the DebugView utility cannot be run at the
# same time as they would both be competing to read debug messages and each of
# them would end up capturing a different subset of the messages.
#
#

import sys
import mmap
import struct
import win32api
import win32event
import threading

class LogDbgView:
    """LogDbgView is the base class of LogDbgViewReal.

    The subclass LogDbgViewReal logs debug view information.  An instance of
    LogDbgView does NOT log debug information.

    The factory method LogDbgView.makeLogDbgView has a parameter,
    log_debug_strings, that determines whether to make an instance of this class
    or the LogDbgViewReal class which will actually do the debug logging.

    Thus it is possible to write one path through the code with a variable that
    determines whether or not to capture and log the debug information, like
    this:

        with LogDbgView.makeLogDbgView(log_debug_strings, 'logfile.txt') as ldv2:
            do_something()
            do_somethingelse()
            do_anotherthing()

    As opposed to having two paths through the code depending on whether or not
    you want to capture and log the debug information, like this:

        if log_debug_strings == True:
            with LogDbgViewReal('logfile.txt') as ldv2:
                do_something()
                do_somethingelse()
                do_anotherthing()
        else:
            do_something()
            do_somethingelse()
            do_anotherthing()
        
    """

    def __init__(self, log_file_name):
        """Construct LogDbgView object instance.

        Since this base class does not actually log the debug information, this
        constructor does nothing.

        Args:
            self: object instance
            log_file_name: name of the file for logging the debug information
            
        """
        pass

    def start(self):
        """Does nothing.

        Since this base class does not actually log the debug information, this
        method does nothing.

        This method is present as it is part of the API of the LogDbgViewReal
        subclass (as inherited from threading.Thread).

        Args:
            self: object instance
            log_file_name: name of the file for logging the debug information
            
        """
        pass

    def close(self):
        """Does nothing.

        Since this base class does not actually log the debug information, this
        method does nothing.

        This method is present as it is part of the API of the LogDbgViewReal
        subclass.

        Args:
            self: object instance
            
        """
        pass

    def __enter__(self):
        """For use with the "with" statement's context manager protocol.

        This method is not meant to be explicitly called, as the "with"
        statement will call it.

        Args:
            self: object instance
            
        """
        self.start()

    def __exit__(self, type, value, traceback):
        """For use with the "with" statement's context manager protocol.

        This method is not meant to be explicitly called, as the "with"
        statement will call it.

        Args:
            self: object instance
            
        """
        self.close()

    @classmethod
    def makeLogDbgView(cls, log_debug_strings, log_file_name):
        """Make either a LogDbgView or LogDbgViewReal object instance.

        Depending on the log_debug_strings argument it will create either a
        LogDbgView instance or a LogDbgViewReal instance.

        Args:
            cls: class
            log_debug_strings: when True logs the debug strings, otherwise does
                not log the debug strings
            log_file_name: the file for logging debug view information

        """
        log_dbg_view = LogDbgViewReal if log_debug_strings == True else LogDbgView
        return log_dbg_view(log_file_name)

    @staticmethod
    def test(log_debug_strings):
        """Tests the LogDbgView class.

        Depending on the log_debug_strings argument it will create either a
        LogDbgView instance or a LogDbgViewReal instance.

        Tests both explicitly calling the start() and close() methods as well
        as having those methods called implicitly by the "with" statement's
        context manager protocol.

        Args:
            log_debug_strings: when True logs the debug strings, otherwise does
                not log the debug strings

        """
        #
        # test explicitly calling start() and close() methods()
        #
        ldv1 = LogDbgView.makeLogDbgView(log_debug_strings, 'logfile1.txt')
        ldv1.start()
        win32api.OutputDebugString('foo')
        win32api.OutputDebugString('bar')
        win32api.OutputDebugString('baz')
        ldv1.close()
        #
        # test using "with" statement, where start() and close() are implicitly
        # called by context manager protcol
        #
        with LogDbgView.makeLogDbgView(log_debug_strings, 'logfile2.txt') as ldv2:
            win32api.OutputDebugString('hi')
            win32api.OutputDebugString('there')
            win32api.OutputDebugString('world')
            win32api.OutputDebugString('!')


class LogDbgViewReal(threading.Thread, LogDbgView):
    """LogDbgViewReal is a class that logs debug view information.

    Captures the debug view information as a background thread, while the main
    thread continues execution.

    Attributes:
        log_file: the file for logging debug view information
        buffer_ready: a windows event to indicate that the background thread is
            ready for the next debug message
        data_ready: a windows event to indicate that the next debug message is
            present in the buffer so that the background thread can read it
        stop: an event to send to the background thread to tell it to stop
            logging
        buffer_length: the length of the memory mapped buffer to read for debug
            information
        buffer: the memory mapped buffer to read for debug information
        
    """

    def __init__(self, log_file_name):
        """Construct LogDbgViewReal object instance.

        Opens the log file for writing and sets up events and memory mapped
        buffer needed to capture the debug information.

        Args:
            self: object instance
            log_file_name: name of the file for logging the debug information
            
        """
        super().__init__()
        self.log_file = open(log_file_name, 'w')
        self.buffer_ready = win32event.CreateEvent(None, 0, 0, "DBWIN_BUFFER_READY")
        self.data_ready = win32event.CreateEvent(None, 0, 0, "DBWIN_DATA_READY")
        self.stop = win32event.CreateEvent(None, 0, 0, None)
        self.buffer_length = 4096
        self.buffer = mmap.mmap (0, self.buffer_length, "DBWIN_BUFFER", mmap.ACCESS_WRITE)

    def run(self):
        """Background thread logic for capturing and logging debug information.

        This method is not meant to be explicitly called.  Call the start()
        method instead.

        Args:
            self: object instance
            
        """
        process_id_length = 4
        remaining_length = self.buffer_length - process_id_length
        events = [self.data_ready, self.stop]
        while True:
            win32event.SetEvent(self.buffer_ready)
            result = win32event.WaitForMultipleObjects(events, 0, win32event.INFINITE)
            if result == win32event.WAIT_OBJECT_0:  # data_ready
                self.buffer.seek(0)
                process_id, = struct.unpack('L', self.buffer.read(process_id_length))
                data = self.buffer.read(remaining_length)
                if 0 in data:
                    string = str(data[:data.index(0)], 'UTF-8')
                else:
                    string = str(data, 'UTF-8')
                self.log_file.write('Process {p}: {s}\n'.format(p=process_id, s=string))
            elif result == (win32event.WAIT_OBJECT_0 + 1):  # stop
                break

    def close(self):
        """Closes out the logging of debug information.

        Tells the background thread to stop, waits for the background thread to
        finish, then closes the memory mapped buffer and the log file.
        
        Args:
            self: object instance
        """
        win32event.SetEvent(self.stop)
        self.join()
        self.buffer.close()
        self.log_file.close()
