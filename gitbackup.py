#!/usr/bin/env python2
"""A script to back up a git repository.

This was designed specifically for use in backing up safely to Dropbox,
though it can be used to back up to any path in your filesystem (ie, a mounted
SMB or NFS remote networked directory).
"""

import os
import sys
import urllib

import git

class MirrorWarning(Exception): pass

class MirrorError(Exception): pass

class BackupError(Exception): pass

class Mirror(object):
    
    def __init__(self, remote_name, source, dest):
        self.remote_name = remote_name
        self.source = source
        
        self.errors = []
        self.project_name = os.path.split(source)[1]
        self.remote_path = os.path.join(dest, self.project_name)
        self.remote_url = 'file://%s' % urllib.pathname2url(self.remote_path)
        try:
            self.repo = git.Repo(source)
        except git.errors.InvalidGitRepositoryError:
            # The folder is not managed with git.
            # This mirror is bogus and will be dumped.
            self.repo = None
    
    def __eq__(self, other):
        return self.repo.working_dir == other.repo.working_dir
    
    def prepare(self, force_remote):
        if not self.repo:
            raise MirrorWarning('Source directory not managed by git.')
        if self.source != self.repo.working_dir:
            print self.source, self.repo.working_dir
            raise MirrorWarning('Parent directory is managed by git.')
        if self.repo.is_dirty():
            raise MirrorError('Source repository is dirty.')
        if self.remote_name in [remote.name for remote in self.repo.remotes] \
                and self.repo.remote(self.remote_name).url != self.remote_url \
                and not force_remote:
            raise MirrorError('Remote name %s already in use.' % self.remote_name)
    
    def update(self):
        if self.remote_name not in [remote.name for remote in self.repo.remotes]:
            self.repo.create_remote(self.remote_name, self.remote_url)
        else:
            if self.repo.remote(self.remote_name).url != self.remote_url:
                self.repo.delete_remote(self.repo.remote(self.remote_name))
                self.repo.create_remote(self.remote_name, self.remote_url)
        
        if not os.path.exists(self.remote_path):
            git.Repo.init(self.remote_path, bare=True, mkdir=True)
        
        self.repo.remote(self.remote_name).push(mirror=True)

class BackupManager(object):
    """An object to handle backing up git repositories to a directory.
    """
    def __init__(self, remote_name, sources, dest, recursive=False, force_remote=False):
        self.dest = dest
        self.remote_name = remote_name
        sources = [os.path.abspath(source) for source in sources]
        if recursive:
            self.sources = []
            for source in sources[:]:
                for dirpath, dirname, filenames in os.walk(source):
                    if '.git' in dirpath:
                        continue
                    if dirpath not in self.sources:
                        self.sources.append(dirpath)
        else:
            self.sources = sources
        self.recursive = recursive
        self.force_remote = force_remote
    
    def build_mirrors(self):
        mirrors = []
        for source in self.sources:
            mirror = Mirror(self.remote_name, source, self.dest)
            try:
                mirror.prepare(self.force_remote)
            except MirrorError, reason:
                write_error('Skipping "%s": ' % mirror.source, reason)
            except MirrorWarning, reason:
                if not self.recursive:
                    write_error('Skipping "%s": ' % mirror.source, reason)
            else:
                if mirror in mirrors:
                    raise BackupError('Duplicate project name "%s".' % mirror.source)
                mirrors.append(mirror)
        return mirrors
    
    def update_all(self):
        for mirror in self.build_mirrors():
            mirror.update()

class Options(object):
    
    def __init__(self, args):
        self.prog_name = args.pop(0)
        self.recursive = False
        self.force_remote = False
        self.remote_name = 'gitbackup'
        
        for option in ('-h', '--help'):
            if option in args:
                self.exit_with_usage(0)
        
        for option in ('-r', '-R', '--recursive'):
            if option in args:
                self.recursive = True
                args.remove(option)
        
        for option in ('-f', '--force-remote'):
            if option in args:
                self.force_remote = True
                self.remote_name = None
                args.remove(option)
        
        if '-n' in args:
            i = args.index('-n')
            args.pop(i)
            self.remote_name = args.pop(i)
        
        for arg in args[:]:
            if arg.startswith('--name='):
                self.remote_name = arg[7:]
                args.remove(arg)
        
        if len(args) < 2:
            self.exit_with_usage(1, 'Error -- too few arguments')
        else:
            self.dest = os.path.normpath(args.pop(-1))
            self.sources = [os.path.normpath(src) for src in args]
        
        if not self.remote_name:
            self.exit_with_usage(1, 'A remote name must be specified.')
    
    def exit_with_usage(self, exit_code, message=None):
        lines = [
            'Usage: %s [-h] [-r] [-n REMOTE_NAME] SOURCE... DESTINATION' % self.prog_name,
            '',
            'A script to back up a git repository.'
            '',
            'Arguments:',
            '  -h, --help                Show this help message and exit',
            '  -r, -R, --recursive       Search the supplied source directories',
            '                            recursively for projects to back up.',
            '  -f, --force-remote        Force the deletion of any remotes',
            '                            that use REMOTE_NAME but are created',
            '                            elsewhere. The standard behavior is for',
            '                            the program to quit with an error if it',
            '                            encounters a name conflict. If you',
            '                            enable this option, you must supply a',
            '                            remote name with the -n option.',
            '  -n NAME, --name=NAME      A unique name for the git remote',
            '                            repository used for this backup. Do not',
            '                            use a name that is used for any other',
            '                            remotes set up for any of the projects.',
            '                            The default remote name is gitbackup.',
            '  SOURCE                    A project directory that you wish to',
            '                            back up. You may specify as many as you',
            '                            wish, or use shell wildcards.',
            '  DESTINATION               The base directory into which the',
            '                            backups will be written.',
            ]
        if message:
            lines.insert(0, str(message))
        
        print '\n'.join(lines)
        sys.exit(exit_code)

def write_error(base_msg, reason):
    sys.stderr.write(base_msg)
    sys.stderr.write(str(reason))
    sys.stderr.write('\n')
    sys.stderr.flush()

if __name__ == '__main__':
    opts = Options(sys.argv)
    manager = BackupManager(opts.remote_name, opts.sources, opts.dest,
        opts.recursive, opts.force_remote
        )
    try:
        manager.update_all()
    except BackupError, reason:
        write_error('Backup failed: ', reason)
        sys.exit(1)


