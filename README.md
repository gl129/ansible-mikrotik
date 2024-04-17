# ansible-mikrotik
Microtik Ansible Modules

These ansible modules can configure Mikrotik RouterOS revisions 6 and 7 devices using ssh connection
See action_plugins directory for complete description.
See gl_mikrotik.yml, inventory and group_vars for samples and solutions.

Structure:

```
action_plugins/         Ansible action plugin (Python)
files/                  Mikrotik's files to transfer. scripts, public keys. etc.
filter_plugins/         Ansible filter plugins (Python)
group_vars/             Ansible group variables (YML). Main configuration source.
inventory/              Ansible inventory files (YML)
lookup_plugins/         Ansible lookup plugins (Python)
tasks/                  Ansible directory to include tasks from
ansible.cfg             Ansible main configuration file for Mikrotik plays
gl_mikrotik.yml         Ansible main configuration play. Almost all configs are taken from group_vars folder
```

Play file contains hosts variable in form:
```
hosts: '{{ ansible_limit | mandatory }}'
```
since to run any play should specify 'limit', like:
```
ansible-playbook <play-name> -l <host or group name>
```
!!! DO NOT under any circumstances specify "all" as a limit !!!


Initial load:
```
ansible-playbook gl_mikrotik.yml -l router_name -e initial=1 --tags create-users,packages
ansible-playbook gl_mikrotik.yml -l router_name -e initial=1
```

Increase verbosity to see all processing parameters (-v) or even all mikrotik scripting internals (-vvv)

Useful cmd to see only changed and failed lines/hosts (TERM=xterm):
```
ANSIBLE_FORCE_COLOR=True ansible-playbook gl_mikrotik.yml -l ready | egrep -Ev '^.\[0;3[26]'
```
