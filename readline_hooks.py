
from __future__ import print_function # PY2

import sys
import traceback
import platform
from ctypes import (pythonapi, cdll, cast, 
	c_int, c_char_p, c_void_p, c_size_t, CFUNCTYPE)


WINDOWS = platform.system().lower() == "windows"


def get_libc():
	if WINDOWS:
		return cdll.msvcrt
	else:
		return cdll["libc.so.6"]

def get_file_pointers():
	if WINDOWS:
		iob_func = cdll.ucrtbase.__acrt_iob_func
		iob_func.restype = c_void_p
		iob_func.argtypes = [c_int]
		
		stdin = iob_func(0)
		stdout = iob_func(1)
		
	else:
		runtime = cdll[None]
		
		stdin = c_void_p.in_dll(runtime, "stdin").value
		stdout = c_void_p.in_dll(runtime, "stdout").value
	
	return stdin, stdout


HOOKFUNC = CFUNCTYPE(c_char_p, c_void_p, c_void_p, c_char_p)

LIBC = get_libc()
strncpy = LIBC.strncpy
strncpy.restype = c_char_p
strncpy.argtypes = [c_char_p, c_char_p, c_size_t]

PyMem_Malloc = pythonapi.PyMem_Malloc
PyMem_Malloc.restype = c_size_t
PyMem_Malloc.argtypes = [c_size_t]

PyOS_ReadlineFunctionPointer = c_void_p.in_dll(pythonapi, "PyOS_ReadlineFunctionPointer")

STDIN_FILE_POINTER, STDOUT_FILE_POINTER = get_file_pointers()


def get_function_address(func):
	return cast(func, c_void_p).value

def new_zero_terminated_string(b):
	p = PyMem_Malloc(len(b) + 1)
	strncpy(cast(p, c_char_p), b, len(b) + 1)
	return p


def readline_wrapper(stdin_fp, stdout_fp, prompt_bytes):
	try:
		prompt = prompt_bytes.decode(sys.stdout.encoding)
		try:
			line = readline_hook(prompt)
		except KeyboardInterrupt:
			return 0
		else:
			line_bytes = line.encode(sys.stdin.encoding)
			return new_zero_terminated_string(line_bytes)
	except:
		print("An error occured in a readline hook", file=sys.stderr)
		traceback.print_exc(file=sys.stderr)
		return new_zero_terminated_string(b"\n")

readline_hook = None
readline_hook_ref = HOOKFUNC(readline_wrapper)


def get_readline_hook():
	our_address = cast(readline_hook_ref, c_void_p).value
	actual_address = PyOS_ReadlineFunctionPointer.value
	
	if actual_address == our_address:
		return readline_hook
	elif actual_address is None:
		return None
	
	print(actual_address)
	
	readline_bytes = HOOKFUNC(actual_address)
	
	def readline(prompt=""):
		prompt_bytes = prompt.encode(sys.stdout.encoding)
		line_bytes = readline_bytes(STDIN_FILE_POINTER, STDOUT_FILE_POINTER, prompt_bytes)
		if line_bytes is None: 
			raise KeyboardInterrupt
		line = line_bytes.decode(sys.stdin.encoding)
		return line
	
	readline.__readline_bytes__ = readline_bytes
	return readline

def set_readline_hook(hook):
	global readline_hook
	
	if hook is None:
		address = 0
	elif hasattr(hook, "__readline_bytes__"):
		address = get_function_address(hook.__readline_bytes__)
	else:
		readline_hook = hook
		address = get_function_address(readline_hook_ref)
	
	PyOS_ReadlineFunctionPointer.value = address


def stdio_readline(prompt=""):
	sys.stdout.write(prompt)
	sys.stdout.flush()
	return sys.stdin.readline()


sys.__readlinehook__ = get_readline_hook()

