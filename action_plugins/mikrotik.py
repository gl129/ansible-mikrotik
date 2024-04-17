#!/usr/bin/python3

# Copyright: (c) 2022-2024, Gennady Lapin <gennady.lapin@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import copy
import itertools
import re
import os
import shutil
import tempfile
import filecmp
from ansible import constants as C
from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleError, AnsibleFileNotFound, AnsibleAction, AnsibleActionFail



special_commands = {
    'cmd':
    {
        'type': str,
        'comment': 'standalone parameter, just run command specified and return result'
    },
    'put':
    {
        'comment': 'scp local file specified with "src" to remote "dst" if is absent or different'
    },
    'fetch':
    {
        'comment': 'scp remote file specified by "src" to local "dst". create .bak if fetched file is different'
    },
    'config':
    {
        'type': list,
        'comment': 'standalone parameter, all other parameters are incapsulated in list and will be run element-by-element as multiple tasks in single task'
    }
}



commands = {
    'path':
    {
        'type': str,
        'allow': [ 'find', 'iterate', 'lines', 'ordered', 'keys', 'set', 'position', 'get', 'get_list', 'get_expr', 'get_expr_list', 'index_by', 'state' ],
        'must': [ 'lines', 'ordered', 'set', 'position', 'get', 'get_list', 'get_expr', 'get_expr_list', 'state' ],
        'comment': 'facility to use, mandatory'
    },
    'find':
    {
        'type': dict,
        'comment': '''values to find objects to get, set, add and remove them
                      keys may be parameters name or _raw, that means "function to calculate"
                      values may:
                          - be equal '!'      - parameter should not be set
                          - begins with '! '  - parameter should be not equal (don't confused with "!value" which in Mikrotik means "equal to not-value)
                          - begins with '~ '  - parameter should match
                          - begins with '!~ ' - parameter should not match
                          - all others        - parameter should be equal
                      NB: "default" and "default-name" keys in "find" have special meaning if no "get*" parameters specified
                          any use of "default" or "default-name" keys in "find" without "get*" keys means finding only by equality with that key and sets all others.
                          also ignore all parameters with prefixes "! ", "~ ", "!~ " which can't be set, but honor "!" which can.'''
    },
    'iterate':
    {
        'type': dict,
        'deny': [ 'position' ],
        'comment': 'loop throw list of find values (cartesian product if two or more specified) !!! DONT WORK AS EXPECTED !!!'
    },
    'lines':
    {
        'type': list,
        'allow': [ 'path', 'state', 'keys' ],
        'comment': 'find multuple objects to check presence, add or remove objects depending on state. can\'t change existing values.'
    },
    'ordered':
    {
        'type': list,
        'allow': [ 'path', 'state', 'keys', 'position' ],
        'comment': 'same as "lines" but additionaly check and retain positions'
    },
    'keys':
    {
        'type': list,
        'state': [ 'adjust' ],
        'must': [ 'lines', 'ordered' ],
        'comment': 'list of key-parameters to search and modify existing values. empty list mean "all parameters are keys". use only with "adjust" state'
    },
    'set':
    {
        'type': dict,
        'deny': [ 'get', 'get_list', 'get_expr', 'get_expr_list' ],
        'comment': 'set objects values'
    },
    'reset':
    {
        'type': dict,
        'deny': [ 'get', 'get_list', 'get_expr', 'get_expr_list' ],
        'comment': 'set objects values'
    },

    'position':
    {
        'type': int,
        'deny': [ 'get', 'get_list', 'get_expr', 'get_expr_list' ],
        'comment': 'move object to specified position. with "ordered" sets first position to check or add'
    },
    'get':
    {
        'type': dict,
        'comment': 'get values of single object in one- or multi-line facilities'
    },
    'get_list':
    {
        'type': dict,
        'must': [ 'find', 'iterate' ],
        'deny': [ 'get' ],
        'comment': 'get values of multiple objects'
    },
    'get_expr':
    {
        'type': dict,
        'deny': [ 'get', 'get_list' ],
        'comment': 'get expression from values of single object in one- or multi-line facilities'
    },
    'get_expr_list':
    {
        'type': dict,
        'must': [ 'find', 'iterate' ],
        'deny': [ 'get', 'get_list', 'get_expr' ],
        'comment': 'get expression from values of multiple objects'
    },
    'index_by':
    {
        'type': str,
        'must': [ 'get', 'get_list', 'get_expr', 'get_expr_list' ],
        'comment': 'get values of single object in one- or multi-line facilities'
    },
    'state':
    {
        'type': str,
        'comment': 'state of object we want to have'
    }
}



states = {
    'present': {
        'comment': 'object should be present. if absent - add, if different - set, if misplaced - move.'
    },
    'absent': {
        'deny': [ 'set', 'get' ],
        'comment': 'objects should be absent. if present - remove. permit multiple objects in one find.'
    },
    'enabled': {
        'deny': [ 'set', 'get' ],
        'comment': 'objects should be enabled. permit multiple objects in one find.'
    },
    'disabled': {
        'deny': [ 'set', 'get' ],
        'comment': 'objects should be disabled. permit multiple objects in one find.'
    },
    'find-only': {
        'deny': [ 'set', 'get' ],
        'comment': 'fail if object is absent, change nothing. check position if specified.'
    },
    'count-only': {
        'deny': [ 'set', 'get' ],
        'comment': 'return count of objects found. don\'t fail, if notfound return 0.'
    },
    'move-only': { # same ad notfound-is-failed
        'must': [ 'position' ],
        'deny': [ 'set', 'get' ],
        'comment': 'fail if oblect is absent, move it if misplaced, change no values'
    },
    'notfound-is-failed': {
        'comment': '''fail if object is not found. set if different, move if misplaced, get values if required
                      - "set" - no add. only set, fail if not found
                      - "position" - only move, fail if not found
                      - "get" - default behavior
                      - "get_list" - fail if object not found !!! WRONG !!! 
                      - "lines", "ordered" or nothing but "iterate" and "find" - (almost) the same as find-only'''
    },
    'notfound-is-ok': {
        'comment': '''continue processing if object or value not found
                      - "set" - only set. no add, do nothing if not found
                      - "position" - do nothing if object or position to move not found
                      - "get", "get_list" - return empty value if not found
                      - "lines", "ordered" or nothing but "iterate" and "find" - (almost) do nothing. no add, no change, no reposition'''
    },
    'skip-empty': {
        'must': [ 'get_expr', 'get_expr_list' ],
        'comment': 'skips empty values'
    },
    'check': {
        'must': [ 'lines', 'ordered' ],
        'comment': 'check actual and configured sets by count actual objects and search configured ones.'
    },
    'replace': {
        'must': [ 'lines', 'ordered' ],
        'comment': '''full replacement of multiline path facility by lines provided ONLY if comparison fail. can be used with "lines" or "ordered".
                      special meaning of "default" and "default-name" keys is preserved as with "find"'''
    },
    'adjust': {
        'must': [ 'keys' ],
        'comment': 'almost the same as replace, but safer, softer and longer. modify existing, adds missing and remove stale records.'
    }
}



examples = {
    'one-line object': {
        'comment': '''- name: DNS settings
                        vars:
                          dns_settings:
                            servers: [ 1.1.1.1, 8.8.8.8 ]
                            allow-remote-requests: yes
                        mikrotik:
                          path: /ip dns
                          set: '{{ dns_settings | mandatory }}'
                   '''
    },
    'multiline object': {
        'comment': '''- name: Ethernet interfaces
                        vars:
                          ethernets:
                            - { name: eth1-fiber, default-name: ether1, l2mtu: 10218 }
                            - { name: eth2-LAN, default-name: ether2 }
                            - { name: eth3-FOREIGN, default-name: ether3 }
                            - { name: '{{ WAN1.interface }}', default-name: ether4, mac-address: '{{ WAN1.mac_address | default(omit) }}' }
                            - { name: '{{ WAN2.interface }}', default-name: ether5, mac-address: '{{ WAN2.mac_address | default(omit) }}' }
                            - { name: eth6-free, default-name: ether6 }
                            - { name: eth7-free, default-name: ether7 }
                            - { name: eth8-free, default-name: ether8 }
                            - { name: sfp1-fiber, default-name: sfp-sfpplus1, l2mtu: 10218, speed: 10Gbps }
                            - { name: sfp2-fiber, default-name: sfp1, l2mtu: 10218, auto-negotiation: no, speed: 1Gbps }
                            - { name: sfp2-fiber, default-name: combo1, l2mtu: 10218, combo-mode: sfp, auto-negotiation: no, speed: 1Gbps }
                        mikrotik:
                        path: /interface ethernet
                        state: notfound-is-ok
                        lines: '{{ ethernets | default([]) }}'
                   '''
    },
    'get hardware info': {
        'comment': '''- name: Gather Mikrotik facts
                        mikrotik:
                          config:
                          - path: /system resource
                            get:
                              architecture-name:
                              board-name:
                              cpu:
                              cpu-count:
                              platform:
                              uptime:
                              version:
                          - path: /interface ethernet
                            find:
                            get_list:
                              ports: name
                            index_by: default-name
                          - path: /interface
                            find:
                              .id: '*3' # most typical interface, all models
                            get:
                              max_l2mtu: max-l2mtu
                          - path: /system package
                            find:
                              disabled: '!'
                            get_list:
                              packages: version
                            index_by: name
                        register: _mikrotik_gather_ret

                      - set_fact:
                          mikrotik: '{{ raw_values | combine({"OS":os|int}) }}'
                        vars:
                          raw_values: '{{ _mikrotik_gather_ret["return_values"] }}'
                          os: '{{ raw_values.version[0] }}'
                   '''
    },
    'adjusting routing': {
        'comment': '''- name: Routing rules
                        vars:
                         routing_rules_:
                           - { src-address: "!", routing-mark: "!", action: lookup, table: main }
                           - { src-address: "!", routing-mark: "!", action: lookup, table: local-unreachable }
                           - { src-address: "{{ wan1.ip_address }}/32", action: lookup-only-in-table, table: "use-{{ wan1.interface }}-inet" },
                           - { src-address: "{{ wan2.ip_address }}/32", action: lookup-only-in-table, table: "use-{{ wan2.interface }}-inet" },
                           - { src-address: "!", routing-mark: "to-{{ wan1.interface }}", action: lookup-only-in-table, table: "use-{{ wan1.interface }}-inet" },
                           - { src-address: "!", routing-mark: "to-{{ wan2.interface }}", action: lookup-only-in-table, table: "use-{{ wan1.interface }}-inet" },
                           - { src-address: "!", routing-mark: "!", action: lookup, table: "use-{{ wan1.interface }}-inet"}
                           - { src-address: "!", routing-mark: "!", action: lookup, table: "use-{{ wan2.interface }}-inet"}
                           - { src-address: "!", routing-mark: "!", action: unreachable }
                           mikrotik:
                          path: '{{ "/ip route" if mikrotik.OS == 6 else "/routing" }} rule'
                          state: adjust
                          keys: [ 'src-address', 'dst-address', 'routing-mark', 'interface', 'action', 'table' ]
                          ordered: '{{ routing_rules | default([]) }}'
                   '''
    }

}



def str_escape( str_to_escape, force=False ):
    """
    Escape string to use in Mikrotik script
    - all type bracketed and statements passed as-is
    - booleans and boolean-like strings passed using Mikrotik boolean representation yes/no
    - lists are translated to [:toarray ...]
    - others treated as string and passed doublequoted and escaped
    - if force parameter is true ANY given string is treated as string and passed doublequoted and escaped
    """
    if str_to_escape is None or len(str(str_to_escape)) == 0:
        return '""'
    if force == False:
        if isinstance(str_to_escape,list):
            return f'[:toarray "{",".join(map(str,str_to_escape))}"]'
        elif isinstance(str_to_escape,bool):
            return 'yes' if str_to_escape else 'no'
        elif isinstance(str_to_escape,str):
            if str_to_escape.lower() in ['yes','true','on']:
                return 'yes'
            elif str_to_escape.lower() in ['no','false','off']:
                return 'no'
            elif str_to_escape[0] in ['"','(','[']:
            # don't add '{' - script will fail
                return str_to_escape
    return '"'+str(str_to_escape).replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('\n','\\r\\n')+'"'



class ActionModule(ActionBase):

#    _VALID_ARGS = frozenset(( 'cmd', 'config', 'path', 'find', 'iterate', 'lines', 'ordered', 'get', 'get_list', 'index_by', 'set', 'position', 'state' ))

    task_vars = {}



    def execute_cmd( self, cmd ):
        if 'romon_host_id' in self.task_vars:
            cmd = f'/tool romon ssh {self.task_vars["romon_host_id"]} command={str_escape(cmd,True)}'
        result = self._low_level_execute_command( cmd, executable=False )
        r_out = result.get('stdout')
        if (
               result.get('failed')
            or result.get('rc') != 0
            or '<FAILED>' in r_out
            or 'failure: ' in r_out
            or 'syntax error' in r_out
            or 'input does not match' in r_out
            or 'expected' in r_out
            or 'syntax error' in r_out
            or 'bad command' in r_out
            or 'invalid value' in r_out
            or 'no such item' in r_out
            or 'missing value' in r_out
            or 'invalid internal item number' in r_out
            or 'ambiguous value' in r_out
        ):
            self._display.v( f'failed command: {cmd}' )
            m = re.search( r'\(line [0-9]+ column ([0-9]+)\)', r_out )
            if m is not None:
                self._display.v( f'failed position:{"^".rjust(int(m.group(1))," ")}' )
            result['failed'] = True
            result['msg'] = r_out

        if '<CHANGED>' in r_out:
            result['changed'] = True

        if '<VALUES>' in r_out:
            return_values = {}
            for line in result['stdout_lines']:
                m = re.search( r'^(.+)[|](.*)[|](.*)$', line )
                if m is not None:
                    key = m.group(1)
                    index = m.group(2)
                    value = m.group(3)
                    if index == '':
                        return_values[key] = value
                    else:
                        if isinstance( return_values.get(key), dict ) == False:
                            return_values[key] = {}
                        if index == '-':
                            if return_values[key].keys():
                                index = max( return_values[key].keys() ) + 1
                            else: index = 0
                        return_values[key][index] = value
            result['return_values'] = return_values

        return result



    def run( self, tmp=None, task_vars=None ):

        if task_vars is None:
            task_vars = dict()
        self.task_vars = task_vars

        super(ActionModule,self).run( tmp, task_vars )
        del tmp

        args = self._task.args
       
        # special parameters

        if len(args) > 1 and any( i in args for i in special_commands ):
            raise AnsibleActionFail ( 'Incompatible top-level parameters specified' )

        if 'cmd' in args:
            display_command = 'cmd'
            cmd = args.get( 'cmd' )
            ret = self.execute_cmd( cmd ) if self._task.check_mode == False else {}
            ret['changed'] = True
            return ret

        if 'put' in args:
            display_command = 'put'
            local_path = args['put']['src']
            remote_path = args['put']['dest']
            tmp_fd,tmp_name = tempfile.mkstemp()
            try:
                os.close( tmp_fd )
                try:
                    self._connection.fetch_file( remote_path, tmp_name )
                except:
                    pass
                if filecmp.cmp( local_path, tmp_name, False ) == False:
                    if self._task.check_mode == False:
                        self._connection.put_file( local_path, remote_path )
                    return { 'changed': True, 'remote_path': remote_path }
            finally:
                os.remove( tmp_name )
            return {}

        if 'fetch' in args:
            display_command = 'fetch'
            remote_path = args['fetch']['src']
            local_path = args['fetch']['dest']
            tmp_fd,tmp_name = tempfile.mkstemp()
            try:
                os.close( tmp_fd )
                self._connection.fetch_file( remote_path, tmp_name )
                try:
                    if filecmp.cmp( local_path, tmp_name, False ) == True: # files are identical
                        return {}
                except:
                    pass
                if self._task.check_mode == False:
                    try:
                        os.replace( local_path, f'{local_path}.bak' )
                    except:
                        pass
                    try:
                        os.replace( tmp_name, local_path )
                    except:
                        shutil.copy2( tmp_name, local_path )
                return { 'changed': True, 'local_path': local_path }
            finally:
                try:
                    os.remove( tmp_name )
                except:
                    pass
            return {}

        # standart parameters

        if 'config' in args:
            display_command = 'config'
            config = args.get( 'config' )
            if len( config ) == 0:
                raise AnsibleActionFail ( '"config" list is empty - nothing to do' )
            if isinstance(config,list) == False or isinstance(config[0],dict) == False:
                raise AnsibleActionFail ( '"config" should be a list of dicts' )
        elif 'path' in args:
            config = [ args ]
        else:
            raise AnsibleActionFail ( 'There are no "path" parameter specified - nothing to do' )

        return self.process_config( config )



    def process_config( self, config, depth=0 ):
        ###
        ### Process config variable to iterate through subtasks
        ###

        config_result = {}
        display_command = 'CONFIG'

        for p in config:

            subtask_result = {}

            path = p.get( 'path' )
            state = p.get( 'state', 'present' )  # 'present' is the default state
            if isinstance(state,str) == False or state not in states:
                raise AnsibleError( 'Invalid state "%s" specified' % state )

            for a in p:
                if a not in commands:
                    raise AnsibleError( 'Unknown parameter "%s" specified' % a )
                if 'type' in commands[a]:
                    if p[a] is not None and isinstance( p[a], commands[a]['type'] ) == False:
                        raise AnsibleActionFail( 'Parameter "%s" shoult be of "%s" type, but "%s"' % (a, commands[a]['type'], type(p[a]) ) )
                if 'allow' in commands[a]:
                    for i in p:
                        if i != a and i not in commands[a]['allow']:
                            raise AnsibleActionFail( 'Parameter "%s" incompatible with "%s"' % (i, a) )
                if 'deny' in commands[a]:
                    for i in p:
                        if i != a and i in commands[a]['deny']:
                            raise AnsibleActionFail( 'Parameter "%s" should not be used with "%s"' % (i, a) )
                if 'must' in commands[a] and all( i not in commands[a]['must'] for i in p ):
                    raise AnsibleActionFail( 'No necessary parameters specified for parameter "%s"' % a )
                if 'state' in commands[a] and state not in commands[a]['state']:
                    raise AnsibleActionFail( 'Incompatible state "%s" with parameter "%s"' % (state, a) )

            if 'must' in states[state] and all( i not in states[state]['must'] for i in p ):
                raise AnsibleActionFail( 'No necessary parameters specified for state "%s"' % state )
            if 'deny' in states[state]:
                for i in p:
                    if i in states[state]['deny']:
                        raise AnsibleActionFail( 'Parameter "%s" should not be used with state "%s"' % (i, state) )

            ###
            ### Complex and special state processing 
            ###
            if state == 'replace':
                display_command = 'replace'
                check_p = p.copy() # may be "lines" or "ordered" to check position
                check_p['state'] = 'check'
                result = self.process_config( [ check_p ], depth+1 )
                if result.get( 'failed', False ):
                # plan and fact are different - really need to replace
                    absent_p = { 'path': p['path'], 'state': 'absent', 'find': None }
                    present_p = { 'path': p['path'], 'state': 'present', 'lines': (p['lines'] if 'lines' in p else p['ordered']) }
                                                                          # always add in order, "ordered" is not necessary
                    subtask_result = self.process_config( [ absent_p, present_p ], depth+1 )
                    if subtask_result.get( 'failed', False ):
                        return subtask_result
                        
            elif state == 'check':
                display_command = 'check'
                check_p = p.copy() # may be "lines" or "ordered" to check position
                check_p['state'] = 'find-only'
                count_p = { 'path': p['path'], 'state': 'count-only', 'find': None  }
                subtask_result = self.process_config( [ check_p, count_p ], depth+1 )
                if subtask_result.get( 'failed', False ) or 'return_values' in subtask_result and int(subtask_result['return_values']['count']) != len(p['lines'] if 'lines' in p else p['ordered']):
                    return { 'failed': True, 'msg': 'Check failed - configured and actual parameters are different' }

            elif state == 'adjust':
                display_command = 'adjust'
                keys = p['keys']
                ids = []
                # change existing objects using "keys" attributes
                for pos, line in enumerate( p.get('lines',p.get('ordered',[])), start=0 ):
                    finds = {}
                    sets = {}
                    for k in line.keys():
                        if keys == [] or k in keys:
                            finds[k] = line[k]
                        else:
                            sets[k] = line[k]
                    present_p = { 'path': p['path'], 'state': 'present', 'find': finds, 'set': sets }
                    if 'ordered' in p:
                        present_p['position'] = pos
                    get_p = { 'path': p['path'], 'state': 'notfound-is-failed', 'find': finds, 'get': { 'id': '.id' } }
                    result = self.process_config( [ present_p, get_p ], depth+1 )
                    if result.get( 'failed', False ):
                        return result
                    if result.get( 'changed', False ):
                        subtask_result['changed'] = True
                    if 'return_values' in result:
                        ids += [ result['return_values']['id'] ]
                # ensure absence of notconfigured objects
                absent_p = { 'path': p['path'], 'state': 'absent', 'find': { '_raw': f'! ( [:find in={str_escape(ids)} key=$".id"] >=0 )' } }
                result = self.process_config( [ absent_p ], depth+1 )
                if result.get( 'failed', False ):
                    return result
                if result.get( 'changed', False ):
                    subtask_result['changed'] = True

            ###
            ### Plain state processing
            ###
            else:

                ###
                ### Variables preparation
                ###

                sets = '' # key-value pairs for set and compare object arguments in multiline facilities
                cond = '' # condition for values compare in oneline facilities (without find)
                if 'set' in p or 'reset' in p:
                    sets_items = p.get( 'set', p.get( 'reset', {} ) )
                    for k, v in sets_items.items():
                        if v is None :
                            sets += f' {k}'
                        elif v == '!':
                            sets += f' !{k}'
                        else:
                            sets += f' {k}={str_escape(v)}'
                        cond += (' or ' if cond else '') + f'$vals->"{k}"!={str_escape(v)}'
    
                gets = '' # to use in { {gets} } array for keys in get statement and its aliases in output
                if 'get' in p or 'get_list' in p:
                    gets_items = p.get( 'get', p.get( 'get_list', {} ) )
                    for alias, expr in gets_items.items():
                        if expr is None: expr = alias
                        gets += (';' if gets else '') + f'"{alias}"="{expr}"'
                if 'get_expr' in p or 'get_expr_list' in p:
                    gets_items = p.get( 'get_expr', p.get( 'get_expr_list', {} ) )
                    for alias, expr in gets_items.items():
                        if expr is None: expr = f'$"{alias}"'
                        gets += (';' if gets else '') + f'"{alias}"={str_escape(expr,True)}'

                index_by = p.get( 'index_by', '' ) # indexes for return_values
                if index_by:
                    if index_by.startswith('"'): # hard index name if doublequoted
                        index_by = f'''{index_by.strip('"')}'''
#                    else:
#                        # if 'get_expr' in p or 'get_expr_list' in p:  pass        # index_by already correct
#                        if 'get' in p or 'get_list' in p:
#                            index_by = f'$($s->"{index_by}")'

                if 'iterate' in p:
                    _iterate = p.get( 'iterate' )
                    iterate = list( dict( zip(_iterate.keys(),value) ) for value in itertools.product(*_iterate.values()) )
                elif 'lines' in p:
                    iterate = p.get( 'lines' )
                elif 'ordered' in p:
                    iterate = p.get( 'ordered' )
                else:
                    iterate = [{}]

                for iterate_idx, iterate_items in enumerate( iterate, start=0 ):
                    find_any = '' # find string to use in [find {find}] and "add" statements
                    add_set = '' # string to use in "add" and "set" statements
                    find_only = '' # find string to only use in [find {find}] statements
                    find_default = '' # only find by default values if specified, others - sets
                    vals = '' # { {vals} } array for values compare in oneline facilities (without find)
                    if 'find' in p or 'iterate' in p or 'lines' in p or 'ordered' in p:
                        find_items = p.get( 'find', {} )      # empty if not specified
                        if find_items is None: find_items={}  # empty if specified but has no value
                        find_items.update( iterate_items )
                        for k, v in find_items.items():
                            sv = str( v )
                            if k in ['default','default-name']:
                                find_default += f' {k}={str_escape(v)}'
                            elif k in ['comment'] and v in ['!','']:
                                add_set += f' {k}=""'
                                find_only += f' !{k}'
                            elif k == '_raw':
                                find_only += f' {v}'
                            elif v is None:             # { param: null } in ansible
                                find_any += f' {k}'
                            elif v == '!':
                                find_any += f' !{k}'
                            elif sv[0:2] == '! ':
                                find_only += f' {k}!={str_escape(v[2:])}'
                            elif sv[0:2] == '~ ':
                                find_only += f' {k}~{str_escape(v[2:],force=True)}'
                            elif sv[0:3] == '!~ ':
                                find_only += f' !({k}~{str_escape(v[3:])})'
                            else:
                                find_any += f' {k}={str_escape(v)}'
                                vals += (';' if len(vals) > 0 else '') + f'{k}={str_escape(v)}'

                    # complete find string, contains "find", "iterate", "lines" and "ordered" conditions
                    find_complete = f'{find_default}{find_any}{find_only} !dynamic' #if find_default or find_any or find_only else ' true'
                    find_complete_dynamic = f'{find_default}{find_any}{find_only} dynamic' #if find_default or find_any or find_only else ' true'

                    pos = None
                    if 'ordered' in p:
                        pos = iterate_idx + p.get( 'position', 0 )
                        #subtask_result['return_values']['last_pos'] = pos
                    elif 'position' in p:
                        pos = p.get('position')
   
                    ###
                    ### Commands processing
                    ###

                    if 'get' in p:
                    # read values from single record from one- or multiline facilities
                        display_command = 'get'
                        if 'find' in p or 'iterate' in p:
                            find_stm = f'[find where {find_complete}]' # may be empty but must be present - multiline facility
                        else:
                            find_stm = '' # absence of 'find' keywork for oneline facilities
                        index_by = f'$($s->"{index_by}")'
                        cmd = (
                            f'{{'
                          + f'  {path};'
                          + f'  :local g {{ {gets} }};'
                          +(f'  :if ( {find_stm} = "" ) do={{' if find_stm != '' else f'  :if ( false ) do={{') 
                          + f'    :put "no object";'
                          +(f'    :put "<FAILED>"' if state != 'notfound-is-ok' else ':')
                          + f'  }} else={{'
                          + f'    :local s [{path} get {find_stm}];'
                          + f'    :foreach k,n in=$g do={{'
                          +(f'      :if ( [:typeof ($s->n)] = "nothing" ) do={{ :return "<FAILED>: no value with name: $n" }};' if state != 'notfound-is-ok' else '')
                          + f'      :if ( [:typeof ($s->n)] = "array" ) do={{ :put "$k|{index_by}|{{$[:tostr ($s->n)]}}" }}'
                          + f'       else={{ :put "$k|{index_by}|$($s->n)" }}'
                          + f'    }};'
                          + f'    :put "<VALUES>"'
                          + f'  }}'
                          + f'}}'
                        )

                    elif 'get_list' in p:
                    # read values from multiple records returned by find
                        display_command = 'get_list'
                        if index_by == '':
                            index_by = '-'
                        else:
                            index_by = f'$($s->"{index_by}")'
                        cmd = (
                            f'{{'
                          + f'  :local g {{ {gets} }};'
                          + f'  :local x [{path} find where {find_complete}];'
                          +(f'  :if ( [:typeof $x] = "nothing" ) do={{ :return "<FAILED>: no objects and state is notfound-is-failed" }}' if state == 'notfound-is-failed' else '')
                          + f'  :foreach i in=$x do={{'
                          + f'    :local s [{path} get $i];'
                          + f'    :foreach k,n in=$g do={{'
                          +(f'      :if ( [:typeof ($s->n)] = "nothing" ) do={{ :return "<FAILED>: no value with name: $n" }};' if state != 'notfound-is-ok' else '')
                          + f'      :put "$k|{index_by}|$($s->n)"'
                          + f'    }}'
                          + f'  }};'
                          + f'  :put "<VALUES>"'
                          + f'}}'
                        )
                    
                    elif 'get_expr' in p:
                    # calculate expressions from single record from one- or multiline facilities
                        display_command = 'get_expr'
                        if 'find' in p or 'iterate' in p:
                            find_stm = f'[find where {find_complete}]' # may be empty but must be present - multiline facility
                        else:
                            find_stm = '' # absence of 'find' keywork for oneline facilities
                        if index_by == '':
                            index_by = '"-"'
                        else:
                            index_by = f'[[:parse ("$p :return ".{str_escape(index_by,True)})]]'
                        cmd = (
                            f'{{'
                          + f'  :local g {{ {gets} }};'
                          + f'  :local s [{path} get {find_stm}];'
                          + f'  :if ( [:typeof $s] = "nothing" ) do={{ :return "<FAILED>: no object" }};'
                          + f'  :local p;'
                          + f'  :foreach k,v in=$s do={{'
                          +  '    :set $p ($p . " :local \\"$k\\" \\"$v\\";")'
                          + f'  }};'
                          + f'  :foreach n,e in=$g do={{'
                          + f'    :local r [[:parse "$p :return $e"]];'
                          +(f'    :if ( [:len $r] > 0 ) do={{' if state == 'skip-empty' else '')
                          #+ f'      :put ("$n|".[[:parse ("$p :return ".{str_escape(index_by,True)})]]."|$r")'
                          + f'      :put ("$n|".{index_by}."|$r")'
                          +(f'    }}' if state == 'skip-empty' else '')
                          + f'  }};'
                          + f'  :put "<VALUES>"'
                          + f'}}'
                        )
    
                    elif 'get_expr_list' in p:
                    # calculate expressions from multiple records returned by find
                        display_command = 'get_expr_list'
                        if index_by == '':
                            index_by = '"-"'
                        else:
                            index_by = f'[[:parse ("$p :return ".{str_escape(index_by,True)})]]'
                        cmd = (
                            f'{{'
                          + f'  :local g {{ {gets} }};'
                          + f'  :local x [{path} find where {find_complete}];'
                          +(f'  :if ( [:typeof $x] = "nothing" ) do={{ :return "<FAILED>: no objects and state is notfound-is-failed" }}' if state == 'notfound-is-failed' else '')
                          + f'  :foreach i in=$x do={{'
                          + f'    :local s [{path} get $i];'
                          + f'    :local p;'
                          + f'    :foreach k,v in=$s do={{'
                          +  '      :set $p ($p . " :local \\"$k\\" \\"$v\\";")'
                          + f'    }};'
                          + f'    :foreach n,e in=$g do={{'
                          + f'      :local r [[:parse "$p :return $e"]];'
                          +(f'      :if ( [:len $r] > 0 ) do={{' if state == 'skip-empty' else '')
                          + f'        :put ("$n|".{index_by}."|$r")'
                          +(f'      }}' if state == 'skip-empty' else '')
                          + f'    }};'
                          + f'  }};'
                          + f'  :put "<VALUES>"'
                          + f'}}'
                        )

                    elif 'find' in p or 'iterate' in p or 'lines' in p or 'ordered' in p:
                    # modify multiline facility
                        display_command = state
                        if state in [ 'present', 'notfound-is-failed', 'notfound-is-ok', 'move-only']:
                            if state == 'move-only':
                                cmd = ''
                            
                            elif find_default:
                                cmd = (
                                    f'{path}; '
                                  + f':if ( [find where {find_default}] = "" ) do={{'
                                  +(f'  :return "<FAILED>: default object not found" ' if state != 'notfound-is-ok' else ':put "not found, it''s ok"')
                                  + f'}} else={{'
                                  + f'  :if ( [find where {find_complete}{sets}] = "" ) do={{'
                                  +(f'    set [find where {find_default}] {find_any}{add_set}{sets};' if self._task.check_mode == False else '')
                                  + f'    :put "<CHANGED>"'
                                  + f'  }}'
                                  + f'}} '
                                )

                            else:
                                cmd = (
                                    f'{path}; '
                                  + f':if ( [find where {find_complete}] = "" ) do={{'
                                  +(f'  remove [find where {find_complete_dynamic}];' if self._task.check_mode == False and state == 'present' else '') # preremove dynamic entries if any
                                  +(f'  add {find_any}{add_set}{sets};' if self._task.check_mode == False and state == 'present' else '')
                                  +(f'  :put "<CHANGED>"' if state == 'present' else '')
                                  +(f'  :return "<FAILED>: object not found and state is notfound-is-failed" ' if state == 'notfound-is-failed' else '')
                                  +(f'  :put "not found, it''s ok"' if state == 'notfound-is-ok' else '')
                                  + f'}} '
                                )

                                if 'set' in p or 'reset' in p or find_default:
                                    cmd += (
        	                            f'else={{'
                                      + f'  :if ( [find where {find_complete}{sets}] = "" ) do={{'
                                      +(f'    set [find where {find_complete}] {sets};' if self._task.check_mode == False else '')
                                      + f'    :put "<CHANGED>"'
                                      + f'  }}'
                                      + f'}} '
                                   )
                            
                            if pos is not None:
                                cmd += ( ('; ' if cmd else '')
                                  + f'{path}; '
                                  + f'{{' 
                                  + f'  :if ( [find where {find_complete}{sets}] = "" ) do={{'
                                  + f'    :put "object to move not exists";' 
                                  +(f'    :put "<FAILED>"' if state != 'notfound-is-ok' else '')
                                  + f'  }} else={{'
                                  + f'    :local v ([get [find where {find_complete}{sets}]]->".id");'
                                  + f'    :local p ([print as-value]->{pos}->".id");'
                                  + f'    :if ( [:typeof $p] = "nothing" ) do={{'
                                  + f'      :put "position {pos} to move not exists";'
                                  +(f'      :put "<FAILED>";' if state != 'notfound-is-ok' else '')
                                  + f'    }} else={{'
                                  + f'      :if ( p != v ) do={{'
                                  +(f'        move $v destination={pos};' if self._task.check_mode == False else '')
                                  + f'        :put "<CHANGED>"'
                                  + f'      }}'
                                  + f'    }}'
                                  + f'  }}'
                                  + f'}}'
                                )

                        elif state == 'absent':
                            if find_default:
                                # can't remove default objects
                                raise AnsibleActionFail( 'Default objects can\'t be removed, don\'t specify "default" or "default-name" parameters' )
                            cmd = (
                                f'{path}; '
                              + f':if ( [find where {find_complete} !default !builtin] != "" ) do={{' # builtin - for /interface list
                              +(f'  remove [find where {find_complete} !default !builtin];' if self._task.check_mode == False else '')
                              + f'  :put "<CHANGED>"'
                              + f'}}'
                            )

                        elif state == 'find-only':
                            cmd = f':if ( [{path} find where {find_complete}] = "" ) do={{ :return "<FAILED>: not found" }};'
                            if pos is not None:
                                cmd += (
                                    f'{{' 
                                  + f'  :local v ([{path} get [find where {find_complete}{sets}]]->".id");'
                                  + f'  :local p ([{path} print as-value]->{pos}->".id");'
                                  + f'  :if ( p != v ) do={{ :return "<FAILED>: not in desired place" }}'
                                  + f'}}'
                                )

                        elif state in [ 'enabled', 'disabled' ]:
                            fail_state = ( 'disabled' if state == 'enabled' else '!disabled' )
                            state_cmd = state[0:-1]
                            cmd = (
                                f'{path}; '
                              + f':if ( [find where {find_complete}] = "" ) do={{'
                              + f'  :put "<FAILED>: object does not exists"'
                              + f'}} else={{'
                              + f'  :if ( [find where {find_complete} {fail_state}] != "" ) do={{'
                              +(f'    {state_cmd} [find where {find_complete} {fail_state}];' if self._task.check_mode == False else '')
                              + f'    :put "<CHANGED>"'
                              + f'  }}'
                              + f'}}'
                            )

                        elif state == "count-only":
                            cmd = f':put "count||$[:len [{path} find where {find_complete} !builtin]]"; :put "<VALUES>"'  # builtin for interface lists only
    
                        else:
                            raise AnsibleActionFail( 'Unsupported state "%s" modifying multiline facility (find parameters presents)' % state )
    
                    else:
                        display_command = 'set'
                        if not 'set' in p:
                            raise AnsibleActionFail( 'No necessary parameters specified - no finds, no gets, no sets' )
                        if state == 'present':
                        # modify oneline facility
                            cmd = (
                                f'{{'
                              + f'  :local vals [{path} get];'
                              + f'  :if ( {cond} ) do={{'
                              +(f'    {path} set {sets};' if self._task.check_mode == False else '')
                              + f'    :put "<CHANGED>"'
                              + f'  }}'
                              + f'}}'
                            )
                        else:
                            raise AnsibleActionFail( 'Unsupported state "state" with oneline facility (there are no find parameters)' % state )

                    if self._task.check_mode:
                        cmd = cmd.replace( '<FAILED>', '<CHANGED>' )

                    cmd_result = self.execute_cmd( cmd )

                    try:    term_cols,term_lines = os.get_terminal_size()
                    except: term_cols = 1000

                    cmd_display = f'[{self.task_vars.get("inventory_hostname")}] => ({display_command}) {path}:{find_complete if find_complete!=" true" else ""}{sets} {gets}'
                    cmd_display_condition = (self._display.verbosity > 0 and (len(config) > 1 or 'lines' in p or 'ordered' in p or 'iterate' in 'p' or not ('find' in p or 'iterate' in p or 'lines' in p or 'ordered' in p)))
                    if cmd_result.get( 'failed', False ):
                        self._display.display( f'failed: {cmd_display}'[0:term_cols], C.COLOR_ERROR )
                        return cmd_result
                    elif cmd_result.get( 'changed', False ):
                        subtask_result['changed'] = True
                        if cmd_display_condition:
                            self._display.display( f'changed: {cmd_display}'[0:term_cols], C.COLOR_CHANGED )
                    else:
                        if cmd_display_condition:
                            self._display.display( f'ok: {cmd_display}'[0:term_cols], C.COLOR_OK )
                    if 'return_values' in cmd_result:
                        v = {}
                        v.update( config_result.get( 'return_values', {} ) )
                        v.update( cmd_result['return_values'] )
                        config_result['return_values'] = v

            # subtask ends here
            if subtask_result.get( 'changed', False ):
                config_result['changed'] = True

            cmd_display = f'[{self.task_vars.get("inventory_hostname")}] => ({display_command}) {path}'
            if self._display.verbosity == 0 and depth == 0 and (len(config) > 1 or 'lines' in p or 'ordered' in p or 'iterate' in 'p'):
                if subtask_result.get( 'changed', False ):
                    self._display.display( cmd_display, C.COLOR_CHANGED )
                else:
                    self._display.display( cmd_display, C.COLOR_OK )
          
            if subtask_result.get( 'changed', False ):
                config_result['changed'] = True

        return config_result



def printer( descr, data ):

    print( "------------------------------" )
    print( f'{descr}:' )
    for cmd in data:
        comment = data[cmd]['comment'].replace( '\n', '\n  ' )
        type = ' (' + re.sub( "^.*'([a-z]+)'.*$", '\\1', str( data[cmd]['type'] ) ) + ')' if 'type' in data[cmd] else ''
        print( f'    {cmd+type:20s}{comment}' )
        if "allow" in data[cmd]:
            print( f'{" ":24s}+ allowed commands: {", ".join(data[cmd]["allow"])}' )
        if "must" in data[cmd]:
            print( f'{" ":24s}+ have to specify: {", ".join(data[cmd]["must"])}' )
        if "state" in data[cmd]:
            print( f'{" ":24s}+ required state: {", ".join(data[cmd]["state"])}' )
        if "deny" in data[cmd]:
            print( f'{" ":24s}+ cant use with: {", ".join(data[cmd]["deny"])}' )

def main():

    print('Ansible action module to programm Mikrotik routers')
    print('All commands honor "check" mode and ignore "diff" mode')
    printer( "Special commands", special_commands )
    printer( "Commands", commands )
    printer( "States", states )
    printer( "Examples", examples )

if __name__ == "__main__":
    main()
