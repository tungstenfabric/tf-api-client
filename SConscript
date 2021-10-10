#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

# src directory

import platform
import subprocess
import sys

subdirs = [
    'schema',
    'api-lib'
]

include = ['#/controller/src', '#/build/include', '#src/contrail-common', '#controller/lib']

libpath = ['#/build/lib']

libs = ['boost_system', 'boost_thread', 'log4cplus', 'pthread']

common = DefaultEnvironment().Clone()

if common['OPT'] == 'production' or common.UseSystemTBB():
    libs.append('tbb')
else:
    libs.append('tbb_debug')

common.Append(LIBPATH = libpath)
common.Prepend(LIBS = libs)

common.Append(CCFLAGS = '-Wall -Werror -Wsign-compare')
gpp_version = subprocess.check_output(
    "g++ --version | grep g++ | awk '{print $3}'",
    shell=True).rstrip()
gpp_version_major = int(gpp_version.split(".")[0])
if gpp_version == "4.8.5" or gpp_version_major >= 8:
    common.Append(CCFLAGS =['-Wno-narrowing', '-Wno-conversion-null'])
    if gpp_version_major >= 8:
        # auto_ptr is depricated - dont error on deprication warnings
        common.Append(CCFLAGS = ['-Wno-error=deprecated-declarations', '-Wno-deprecated-declarations'])

if not sys.platform.startswith('darwin'):
    if platform.system().startswith('Linux'):
       if not platform.linux_distribution()[0].startswith('XenServer'):
          common.Append(CCFLAGS = ['-Wno-unused-local-typedefs'])
if sys.platform.startswith('freebsd'):
    common.Append(CCFLAGS = ['-Wno-unused-local-typedefs'])
common.Append(CPPPATH = include)
common.Append(CCFLAGS = [common['CPPDEFPREFIX'] + 'RAPIDJSON_NAMESPACE=contrail_rapidjson'])

BuildEnv = common.Clone()

if sys.platform.startswith('linux'):
    BuildEnv.Append(CCFLAGS = ['-DLINUX'])
elif sys.platform.startswith('darwin'):
    BuildEnv.Append(CCFLAGS = ['-DDARWIN'])

if sys.platform.startswith('freebsd'):
    BuildEnv.Prepend(LINKFLAGS = ['-lprocstat'])


BuildEnv['INSTALL_DOC_PKG'] = BuildEnv['INSTALL_DOC'] + '/contrail-docs/html'
BuildEnv['INSTALL_MESSAGE_DOC'] = BuildEnv['INSTALL_DOC_PKG'] + '/messages'


for dir in subdirs:
    BuildEnv.SConscript(dir + '/SConscript',
                         exports='BuildEnv',
                         variant_dir=BuildEnv['TOP'] + '/' + dir,
                         duplicate=0)
