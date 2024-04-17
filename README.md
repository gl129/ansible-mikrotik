# ansible-mikrotik
Microtik Ansible Modules

These ansible modules can configure Mikrotik RouterOS revisions 6 and 7 devices using ssh connection
See action_plugins directory for complete description.
See gl_mikrotik.yml, inventory and group_vars for samples and solutions.

Structure:
action_plugins/         Ansible action plugin (Python)
files/                  Mikrotik's files to transfer. scripts, public keys. etc.
filter_plugins/         Ansible filter plugins (Python)
group_vars/             Ansible group variables. Main configuration source.
inventory/              Ansible inventory files
tasks/                  Ansible directory to include tasks from
ansible.cfg             Ansible main configuration file for Mikrotik plays
gl_mikrotik.yml         Ansible main configuration play. Almost all configs are taken from group_vars folder
