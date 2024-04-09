#!/usr/bin/env python

import argparse
import glob
import json
import os
import re
import string
import sys
import subprocess
import shutil
import urllib.request
import tarfile

BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin')
GN_OPTIONS = {
	'treat_warnings_as_errors' : False,
	'fatal_linker_warnings' : False,
	'use_jumbo_build' : True, # removed in V8 version 8.1
	#'symbol_level' : 1,
	'v8_enable_fast_mksnapshot' : False,
	'v8_enable_fast_torque' : False,
	'v8_enable_verify_heap' : False, # to fix VC++ Linker error in Debug configuratons
	#'v8_optimized_debug' : False,
	#'v8_use_snapshot' : True,
	'v8_use_external_startup_data' : False,
	#'v8_enable_handle_zapping' : True,
	#'v8_check_header_includes' : True,
	#'v8_win64_unwinding_info' : False,
	#'dcheck_always_on' : True,
	#'is_clang': USE_CLANG,
	'use_custom_libcxx' : False,
}

def parse_to_dict(action, parser, namespace, values, option_string):
	dict = getattr(namespace, action.dest, {})
	for item in values:
		key, value = item.split('=', 1)
		# distutils.util.strtobool treats 0/1 also as bool values
		try:
			dict[key] = int(value)
		except:
			if value.lower() in ['true', 'yes', 'on']:
				dict[key] = True
			elif value.lower() in ['false', 'no', 'off']:
				dict[key] = False
			else:
				dict[key] = value
	setattr(namespace, action.dest, dict)

arg_parser = argparse.ArgumentParser(description='Build V8 from sources', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
arg_parser.add_argument('--no-fetch',
	dest='NOFETCH',
	action='store_true',
	default=False,
	help='Do not fetch sources')
arg_parser.add_argument('--no-git',
	dest='NOGIT',
	action='store_true',
	default=False,
	help='Download tarball instead of Git fetch')
arg_parser.add_argument('--read-version',
	dest='READ_VERSION',
	action='store_true',
	default=False,
	help='Read actual V8 version from v8-version.h , do no build')
arg_parser.add_argument('--url',
	dest='V8_URL',
	default='https://chromium.googlesource.com/v8/v8.git',
	help='Source url')
arg_parser.add_argument('--version',
	dest='V8_VERSION',
	default='lkgr',
	help='Version tag or branch name')
arg_parser.add_argument('--platform',
	dest='PLATFORMS',
	nargs='+',
	choices=['x86', 'x64', 'arm64'],
	default=['x86', 'x64', 'arm64'],
	help='Target platforms')
arg_parser.add_argument('--config',
	dest='CONFIGURATIONS',
	nargs='+',
	choices=['Debug', 'Release'],
	default=['Debug', 'Release'],
	help='Target configrations')
arg_parser.add_argument('--libs',
	dest='LIBS',
	nargs='+',
	choices=['shared', 'monolith'],
	default=['shared', 'monolith'],
	help='Target libraries')
arg_parser.add_argument('--xp',
	dest='XP_TOOLSET',
	action='store_true',
	default=False,
	help='Build for Windows XP toolset')
arg_parser.add_argument('--use-clang',
	dest='USE_CLANG',
	action='store_true',
	default=False,
	help='Compile with clang')
arg_parser.add_argument('--gn',
	dest='GN',
	default=os.path.join(BIN_DIR, 'gn.exe'),
	help='Path to gn executable')
arg_parser.add_argument('--ninja',
	dest='NINJA',
	default=os.path.join(BIN_DIR, 'ninja.exe'),
	help='Path to ninja executable')
arg_parser.add_argument('--gn-option',
	dest='GN_OPTIONS',
	nargs="+", metavar="KEY=VAL",
	action=type('', (argparse.Action, ), dict(__call__ = parse_to_dict)),
	default=GN_OPTIONS,
	help='Add gn option')

args = arg_parser.parse_args()


# Use only Last Known Good Revision branches
if args.V8_VERSION.count('.') < 2 and all(x.isdigit() for x in args.V8_VERSION.split('.')):
	args.V8_VERSION += '-lkgr' 


print('Parsed args: ', args)


def is_sha1(ref):
	if len(ref) == 40:
		try:
			sha1 = int(ref, 16)
			return True
		except:
			pass
	return False


def git_fetch(url, target):
	# input url like: https://chromium.googlesource.com/v8/v8.git@ref
	if isinstance(url, dict):
		url = url['url']
	parts = url.split('.git@')
	if len(parts) > 1:
		url = parts[0] + '.git'
		ref = parts[1]
	else:
		ref = 'HEAD'

	if args.NOGIT:
		# tarball urls:
		# https://chromium.googlesource.com/chromium/src/build.git/+archive/5c9250c64c70a2f861a435158b57a6d43cd2e7b7.tar.gz
		# https://chromium.googlesource.com/v8/v8.git/+archive/refs/heads/10.6-lkgr.tar.gz
		url += '/+archive/' + ('refs/heads/' if not is_sha1(ref) else '') + ref + '.tar.gz'
	
		print(f'Download {url} into {target}')
		with urllib.request.urlopen(url) as stream:
			with tarfile.open(fileobj=stream, mode="r|gz") as tar:
				tar.extractall(path=target)
	else:
		print(f'Git fetch {url}@{ref} into {target}')

		if not os.path.isdir(os.path.join(target, '.git')):
			subprocess.check_call(['git', 'init', target])
		fetch_args = ['git', 'fetch', '--depth=1', '--update-shallow', '--update-head-ok', '--verbose', url, ref]
		if subprocess.call(fetch_args, cwd=target) != 0:
			print(f'RETRY: {target}')
			shutil.rmtree(target, ignore_errors=True)
			subprocess.check_call(['git', 'init', target])
			subprocess.check_call(fetch_args, cwd=target)
		subprocess.check_call(['git', 'checkout', '-f', '-B', 'Branch_'+ref, 'FETCH_HEAD'], cwd=target)


def rmtree(dir):
	if os.path.isdir(dir):
		shutil.rmtree(dir)

def copytree(src_dir, dest_dir):
	if not os.path.isdir(dest_dir):
		os.makedirs(dest_dir)
	for path in glob.iglob(src_dir):
		shutil.copy(path, dest_dir)


# __main__

## Fetch V8 sources
if args.NOFETCH and os.path.exists('v8'):
	print('Skip fetching, v8 already exists')
else:
	git_fetch(args.V8_URL+'@'+args.V8_VERSION, 'v8')

	## Fetch only required V8 source dependencies
	required_deps = [
		'v8/build',
		'v8/third_party/icu',
		'v8/base/trace_event/common',
		'v8/third_party/jinja2',
		'v8/third_party/markupsafe',
		'v8/third_party/googletest/src',
		'v8/third_party/zlib',
		'v8/third_party/abseil-cpp',
	]

	if args.USE_CLANG:
		required_deps.append('v8/tools/clang')

	Var = lambda name: vars[name]
	Str = lambda str: str
	deps = open('v8/DEPS').read()
	exec(deps)

	for name, url in deps.items():
		if not name.startswith('v8'):
			name = 'v8/' + name
		if name in required_deps:
			git_fetch(url, name)

### Get v8 version from defines in v8-version.h
v8_version_h = open('v8/include/v8-version.h').read()
version = '.'.join(map(lambda name: re.search(r'^#define\s+'+name+r'\s+(\d+)$', v8_version_h, re.M).group(1), \
	['V8_MAJOR_VERSION', 'V8_MINOR_VERSION', 'V8_BUILD_NUMBER', 'V8_PATCH_LEVEL']))
print(f'V8 {version}')
if args.READ_VERSION:
	sys.exit(0)

vs_versions = {
	'12.0': { 'version': '2013', 'toolset': 'v120' },
	'14.0': { 'version': '2015', 'toolset': 'v140' },
	'15.0': { 'version': '2017', 'toolset': 'v141' },
	'16.0': { 'version': '2019', 'toolset': 'v142' },
	'17.0': { 'version': '2022', 'toolset': 'v143' },
}
vs_version = vs_versions[os.environ.get('VisualStudioVersion', '14.0')]
toolset = vs_version['toolset']
vs_version = vs_version['version']

#  VC build tools
vc_tools_install_dir = os.environ.get('VCToolsInstallDir')
if vc_tools_install_dir:
	vs_install_dir = vc_tools_install_dir
else:
	vs_install_dir = os.path.abspath(os.path.join(os.environ['VCINSTALLDIR'], os.pardir))

vc_tools_version = os.environ.get('VCToolsVersion')
if vc_tools_version:
	vs_version = vc_tools_version
	toolset = 'v' + vs_version.replace('.', '')[:3]


env = os.environ.copy()
env['DEPOT_TOOLS_WIN_TOOLCHAIN'] = '0'

if args.XP_TOOLSET:
	if toolset.startswith('v142'):
		raise RuntimeError("XP toolset is not supported")
	env['INCLUDE'] = r'%ProgramFiles(x86)%\Microsoft SDKs\Windows\7.1A\Include;' + env.get('INCLUDE', '')
	env['PATH'] = r'%ProgramFiles(x86)%\Microsoft SDKs\Windows\7.1A\Bin;' + env.get('PATH', '')
	env['LIB'] = r'%ProgramFiles(x86)%\Microsoft SDKs\Windows\7.1A\Lib;' + env.get('LIB', '')
	toolset += '_xp'

subprocess.check_call([sys.executable, 'vs_toolchain.py', 'update'], cwd='v8/build', env=env)
if args.USE_CLANG:
	subprocess.check_call([sys.executable, 'update.py'], cwd='v8/tools/clang/scripts', env=env)

print(f'Visual Studio {vs_version} in {vs_install_dir}')
print(f'C++ Toolset {toolset}')

# Copy GN to the V8 buildtools in order to work v8gen script
if not os.path.exists('v8/buildtools/win'):
    os.makedirs('v8/buildtools/win')
shutil.copy(args.GN, 'v8/buildtools/win')

# Generate LASTCHANGE file
# similiar to `lastchange` hook from DEPS
if os.path.isfile('v8/build/util/lastchange.py'):
	subprocess.check_call([sys.executable, 'lastchange.py', '-o', 'LASTCHANGE'], cwd='v8/build/util', env=env)

if not os.path.isfile('v8/build/config/gclient_args.gni'):
	with open('v8/build/config/gclient_args.gni', 'a') as f:
		f.write('declare_args() { checkout_google_benchmark = false }\n')

def cpp_defines_from_v8_json_build_config(filename):
	json_file = open(filename)
	config = json.load(json_file)

	defines = set()
	if config.get('is_debug', False) or config.get('is_full_debug', False) or config.get('v8_enable_v8_checks', False):
		defines.add('V8_ENABLE_CHECKS')

	if config.get('v8_enable_sandbox', False) or config.get('sandbox', False):
		defines.add('V8_ENABLE_SANDBOX')

	if config.get('v8_enable_pointer_compression', False) or config.get('pointer_compression', False):
		defines.add('V8_COMPRESS_POINTERS')
		defines.add('V8_31BIT_SMIS_ON_64BIT_ARCH')

	if config.get('v8_enable_31bit_smis_on_64bit_arch', False):
		defines.add('V8_31BIT_SMIS_ON_64BIT_ARCH')

	if config.get('v8_deprecation_warnings', False):
		defines.add('V8_DEPRECATION_WARNINGS')

	if config.get('v8_imminent_deprecation_warnings', False):
		defines.add('V8_IMMINENT_DEPRECATION_WARNINGS')

	return ';'.join(defines)


def build(target, options, env, out_dir):
	gn_args = list()
	for k, v in options.items():
		q = '"' if isinstance(v, str) else ''
		gn_args.append(k + '=' + q + str(v) + q)
	subprocess.check_call([args.GN, 'gen', '--ninja-executable=' + args.NINJA, out_dir, '--args=' + ' '.join(gn_args).lower()], cwd='v8', env=env)
	subprocess.check_call([args.NINJA, '-C', out_dir, target], cwd='v8', env=env)


PACKAGES = {
	'shared' : ['v8', 'v8.redist', 'v8.symbols'],
	'monolith' : ['v8.monolith'],
}

## Build V8
for arch in args.PLATFORMS:
	arch = arch.lower()
	for lib in args.LIBS:
		cpp_defines = ''
		build_monolith = (lib == 'monolith')
		for conf in args.CONFIGURATIONS:
			### Generate build.ninja files in out.gn/V8_VERSION/toolset/arch/conf/lib directory
			out_dir = os.path.join('out.gn', args.V8_VERSION, toolset, arch, conf, lib)
			options = args.GN_OPTIONS
			options['is_debug'] = options['is_full_debug'] = options['enable_iterator_debugging'] = (conf == 'Debug')
			options['target_cpu'] = arch
			options['is_clang'] = args.USE_CLANG
			options['is_component_build'] = not build_monolith
			options['v8_monolithic'] = build_monolith
			target = 'v8'
			if build_monolith:
				target += '_monolith'
			build(target, options, env, out_dir)
			cpp_defines += """
	<PreprocessorDefinitions Condition="'$(Configuration)' == '{conf}'">{defines};%(PreprocessorDefinitions)</PreprocessorDefinitions>
	""".format(conf=conf, defines=cpp_defines_from_v8_json_build_config(os.path.join('v8', out_dir, 'v8_build_config.json')))

		if arch == 'x86':
			platform = "('$(Platform)' == 'x86' Or '$(Platform)' == 'Win32')"
		else:
			platform = f"'$(Platform)' == '{arch}'"
		condition = f"'$(PlatformToolset)' == '{toolset}' And {platform}"

		## Build NuGet packages
		for name in PACKAGES[lib]:
			## Generate property sheets with specific conditions
			props = open(f'nuget/{name}.props').read()
			props = props.replace('$Condition$', condition)
			if cpp_defines:
				 props = props.replace('<PreprocessorDefinitions />', cpp_defines)
			open(f'nuget/{name}-{toolset}-{arch}.props', 'w+').write(props)

			nuspec = name + '.nuspec'
			print(f'NuGet pack {nuspec} for V8 {version} {toolset} {arch}')
			nuget_args = [
				'-NoPackageAnalysis',
				'-Version', version,
				'-Properties', 'Platform='+arch+';PlatformToolset='+toolset+';BuildVersion='+args.V8_VERSION,
				'-OutputDirectory', '..'
			]
			subprocess.check_call(['nuget', 'pack', nuspec] + nuget_args, cwd='nuget')
			os.remove(f'nuget/{name}-{toolset}-{arch}.props')
