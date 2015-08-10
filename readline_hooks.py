
from __future__ import print_function # PY2

import sys
import traceback
import platform
import ctypes.util
from ctypes import (POINTER, CFUNCTYPE, CDLL, pythonapi, cast, addressof, 
	c_int, c_char_p, c_void_p, c_size_t, py_object)


WINDOWS = platform.system().lower() == "windows"


def get_libc():
	if WINDOWS:
		path = "msvcrt"
	else:
		path = ctypes.util.find_library("c")
		if path is None:
			raise RuntimeError("cannot locate libc")
	
	return CDLL(path)


def get_file_pointers_Python2():
	PyFile_AsFile = pythonapi.PyFile_AsFile
	PyFile_AsFile.restype = c_void_p
	PyFile_AsFile.argtypes = [py_object]
	
	stdin = PyFile_AsFile(sys.stdin)
	stdout = PyFile_AsFile(sys.stdout)
	return stdin, stdout

def get_file_pointers_Unix():
	runtime = CDLL(None)
	stdin = c_void_p.in_dll(runtime, "stdin").value
	stdout = c_void_p.in_dll(runtime, "stdout").value
	return stdin, stdout

def get_file_pointers_msvcrt():
	class FILE(ctypes.Structure):
		_fields_ = [
			("_ptr", c_char_p), 
			("_cnt", c_int), 
			("_base", c_char_p), 
			("_flag", c_int), 
			("_file", c_int), 
			("_charbuf", c_int), 
			("_bufsize", c_int), 
			("_tmpfname", c_char_p), 
		]
	
	msvcrt = CDLL(ctypes.util.find_msvcrt())
	iob_func = msvcrt.__iob_func
	iob_func.restype = POINTER(FILE)
	iob_func.argtypes = []
	
	array = iob_func()
	stdin = addressof(array[0])
	stdout = addressof(array[1])
	return stdin, stdout

def get_file_pointers_ucrtbase():
	ucrtbase = CDLL("ucrtbase")
	iob_func = ucrtbase.__acrt_iob_func
	iob_func.restype = c_void_p
	iob_func.argtypes = [c_int]
	
	stdin = iob_func(0)
	stdout = iob_func(1)
	return stdin, stdout

def get_file_pointers():
	if sys.version_info < (3,):
		return get_file_pointers_Python2()
	elif WINDOWS:
		if sys.version_info >= (3, 5):
			return get_file_pointers_ucrtbase()
		else:
			return get_file_pointers_msvcrt()
	else:
		return get_file_pointers_Unix()


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


#sys.__readlinehook__ = get_readline_hook()

