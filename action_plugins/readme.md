mikrotik.py

```
Ansible action module to programm Mikrotik routers
All commands honor "check" mode and ignore "diff" mode
------------------------------
Special commands:
    cmd (str)           standalone parameter, just run command specified and return result
    put                 scp local file specified with "src" to remote "dst" if is absent or different
    fetch               scp remote file specified by "src" to local "dst". create .bak if fetched file is different
    config (list)       standalone parameter, all other parameters are incapsulated in list and will be run element-by-element as multiple tasks in single task
------------------------------
Commands:
    path (str)          facility to use, mandatory
                        + allowed commands: find, iterate, lines, ordered, keys, set, position, get, get_list, get_expr, get_expr_list, index_by, state
                        + have to specify: lines, ordered, set, position, get, get_list, get_expr, get_expr_list, state
    find (dict)         values to find objects to get, set, add and remove them
                        keys may be parameters name or _raw, that means "function to calculate"
                        values may:
                            - be equal '!'      - parameter should not be set
                            - begins with '! '  - parameter should be not equal (don't confused with "!value" which in Mikrotik means "equal to not-value)
                            - begins with '~ '  - parameter should match
                            - begins with '!~ ' - parameter should not match
                            - all others        - parameter should be equal
                        NB: "default" and "default-name" keys in "find" have special meaning if no "get*" parameters specified
                            any use of "default" or "default-name" keys in "find" without "get*" keys means finding only by equality with that key and sets all others.
                            also ignore all parameters with prefixes "! ", "~ ", "!~ " which can't be set, but honor "!" which can.
    iterate (dict)      loop throw list of find values (cartesian product if two or more specified) !!! DONT WORK AS EXPECTED !!!
                        + cant use with: position
    lines (list)        find multuple objects to check presence, add or remove objects depending on state. can't change existing values.
                        + allowed commands: path, state, keys
    ordered (list)      same as "lines" but additionaly check and retain positions
                        + allowed commands: path, state, keys, position
    keys (list)         list of key-parameters to search and modify existing values. empty list mean "all parameters are keys". use only with "adjust" state
                        + have to specify: lines, ordered
                        + required state: adjust
    set (dict)          set objects values
                        + cant use with: get, get_list, get_expr, get_expr_list
    reset (dict)        set objects values
                        + cant use with: get, get_list, get_expr, get_expr_list
    position (int)      move object to specified position. with "ordered" sets first position to check or add
                        + cant use with: get, get_list, get_expr, get_expr_list
    get (dict)          get values of single object in one- or multi-line facilities
    get_list (dict)     get values of multiple objects
                        + have to specify: find, iterate
                        + cant use with: get
    get_expr (dict)     get expression from values of single object in one- or multi-line facilities
                        + cant use with: get, get_list
    get_expr_list (dict)get expression from values of multiple objects
                        + have to specify: find, iterate
                        + cant use with: get, get_list, get_expr
    index_by (str)      get values of single object in one- or multi-line facilities
                        + have to specify: get, get_list, get_expr, get_expr_list
    state (str)         state of object we want to have
------------------------------
States:
    present             object should be present. if absent - add, if different - set, if misplaced - move.
    absent              objects should be absent. if present - remove. permit multiple objects in one find.
                        + cant use with: set, get
    enabled             objects should be enabled. permit multiple objects in one find.
                        + cant use with: set, get
    disabled            objects should be disabled. permit multiple objects in one find.
                        + cant use with: set, get
    find-only           fail if object is absent, change nothing. check position if specified.
                        + cant use with: set, get
    count-only          return count of objects found. don't fail, if notfound return 0.
                        + cant use with: set, get
    move-only           fail if oblect is absent, move it if misplaced, change no values
                        + have to specify: position
                        + cant use with: set, get
    notfound-is-failed  fail if object is not found. set if different, move if misplaced, get values if required
                        - "set" - no add. only set, fail if not found
                        - "position" - only move, fail if not found
                        - "get" - default behavior
                        - "get_list" - fail if object not found !!! WRONG !!! 
                        - "lines", "ordered" or nothing but "iterate" and "find" - (almost) the same as find-only
    notfound-is-ok      continue processing if object or value not found
                        - "set" - only set. no add, do nothing if not found
                        - "position" - do nothing if object or position to move not found
                        - "get", "get_list" - return empty value if not found
                        - "lines", "ordered" or nothing but "iterate" and "find" - (almost) do nothing. no add, no change, no reposition
    skip-empty          skips empty values
                        + have to specify: get_expr, get_expr_list
    check               check actual and configured sets by count actual objects and search configured ones.
                        + have to specify: lines, ordered
    replace             full replacement of multiline path facility by lines provided ONLY if comparison fail. can be used with "lines" or "ordered".
                        special meaning of "default" and "default-name" keys is preserved as with "find"
                        + have to specify: lines, ordered
    adjust              almost the same as replace, but safer, softer and longer. modify existing, adds missing and remove stale records.
                        + have to specify: keys
------------------------------
Examples:
    one-line object     - name: DNS settings
                          vars:
                            dns_settings:
                              servers: [ 1.1.1.1, 8.8.8.8 ]
                              allow-remote-requests: yes
                          mikrotik:
                            path: /ip dns
                            set: '{{ dns_settings | mandatory }}'
                     
    multiline object    - name: Ethernet interfaces
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
                     
    get hardware info   - name: Gather Mikrotik facts
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
                     
    adjusting routing   - name: Routing rules
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
```
