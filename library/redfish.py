#!/usr/bin/env python
# -*- coding: utf-8 -*-

# (c) 2017-2018, Dell EMC Inc.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#
ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'metadata_version': '1.1'}

DOCUMENTATION = """
module: redfish
version_added: "2.3"
short_description: Out-Of-Band management using Redfish APIs
options:
  category:
    required: true
    default: None
    description:
      - Action category to execute on server
  command:
    required: true
    default: None
    description:
      - Command to execute on server
  baseuri:
    required: true
    default: None
    description:
      - Base URI of OOB controller
  user:
    required: false
    default: root
    description:
      - User for authentication with OOB controller
  password:
    required: false
    default: calvin
    description:
      - Password for authentication with OOB controller
  userid:
    required: false
    default: None
    description:
      - ID of user to add/delete/modify
  username:
    required: false
    default: None
    description:
      - name of user to add/delete/modify
  userpswd:
    required: false
    default: None
    description:
      - password of user to add/delete/modify
  userrole:
    required: false
    default: None
    description:
      - role of user to add/delete/modify
  bootdevice:
    required: false
    default: None
    description:
      - bootdevice when setting boot configuration
  bios_attr_name
    required: false
    default: None
    description:
      - name of BIOS attribute to update
  bios_attr_value
    required: false
    default: None
    description:
      - value of BIOS attribute to update to
  mgr_attr_name
    required: false
    default: None
    description:
      - name of Manager attribute to update
  mgr_attr_value
    required: false
    default: None
    description:
      - value of Manager attribute to update to

author: "jose.delarosa@dell.com", github: jose-delarosa
"""

import os
import requests
import json
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.redfish_utils import RedfishUtils

def main():
    result = {}
    module = AnsibleModule(
        argument_spec = dict(
            category   = dict(required=True, type='str', default=None),
            command    = dict(required=True, type='str', default=None),
            baseuri    = dict(required=True, type='str', default=None),
            user       = dict(required=False, type='str', default='root'),
            password   = dict(required=False, type='str', default='calvin', no_log=True),
            userid     = dict(required=False, type='str', default=None),
            username   = dict(required=False, type='str', default=None),
            userpswd   = dict(required=False, type='str', default=None, no_log=True),
            userrole   = dict(required=False, type='str', default=None),
            bootdevice = dict(required=False, type='str', default=None),
            mgr_attr_name = dict(required=False, type='str', default=None),
            mgr_attr_value = dict(required=False, type='str', default=None),
            bios_attr_name = dict(required=False, type='str', default=None),
            bios_attr_value = dict(required=False, type='str', default=None),
        ),
        supports_check_mode=False
    )

    # Disable insecure-certificate-warning message
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    category   = module.params['category']
    command    = module.params['command']
    bootdevice = module.params['bootdevice']

    # admin credentials used for authentication
    creds = { 'user': module.params['user'],
              'pswd': module.params['password']
    }
    # user to add/modify/delete
    user = { 'userid'   : module.params['userid'],
             'username' : module.params['username'],
             'userpswd' : module.params['userpswd'],
             'userrole' : module.params['userrole']
    }
    # Manager attributes to update
    mgr_attributes = { 'mgr_attr_name'  : module.params['mgr_attr_name'],
                       'mgr_attr_value' : module.params['mgr_attr_value']
    }
    # BIOS attributes to update
    bios_attributes = { 'bios_attr_name'  : module.params['bios_attr_name'],
                        'bios_attr_value' : module.params['bios_attr_value']
    }

    # Build root URI
    root_uri = "https://" + module.params['baseuri']
    rf_uri = "/redfish/v1"
    rf_utils = RedfishUtils(creds, root_uri)

    # Organize by Categories / Commands
    if category == "Inventory":
        # execute only if we find a System resource
        result = rf_utils._find_systems_resource(rf_uri)
        if result['ret'] == False: module.fail_json(msg=result['msg'])

        # General
        if command == "GetSystemInventory":
            result = rf_utils.get_system_inventory()

        # Components
        elif command == "GetPsuInventory":
            result = rf_utils.get_psu_inventory()
        elif command == "GetCpuInventory":
            result = rf_utils.get_cpu_inventory("/Processors")
        elif command == "GetNicInventory":
            result = rf_utils.get_nic_inventory("/EthernetInterfaces")

        # Storage
        elif command == "GetStorageControllerInventory":
            result = rf_utils.get_storage_controller_info()
        elif command == "GetDiskInventory":
            result = rf_utils.get_disk_info()

        # Chassis
        elif command == "GetFanInventory":
            # execute only if we find Chassis resource
            result = rf_utils._find_chassis_resource(rf_uri)
            if result['ret'] == False: module.fail_json(msg=result['msg'])
            result = rf_utils.get_fan_inventory("/Thermal")

        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Accounts":
        # execute only if we find an Account service resource
        result = rf_utils._find_accountservice_resource(rf_uri)
        if result['ret'] == False: module.fail_json(msg=result['msg'])

        if command == "ListUsers":
            result = rf_utils.list_users(user)
        elif command == "AddUser":
            result = rf_utils.add_user(user)
        elif command == "EnableUser":
            result = rf_utils.enable_user(user)
        elif command == "DeleteUser":
            result = rf_utils.delete_user(user)
        elif command == "DisableUser":
            result = rf_utils.disable_user(user)
        elif command == "UpdateUserRole":
            result = rf_utils.update_user_role(user)
        elif command == "UpdateUserPassword":
            result = rf_utils.update_user_password(user)
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "System":
        # execute only if we find a System resource
        result = rf_utils._find_systems_resource(rf_uri)
        if result['ret'] == False: module.fail_json(msg=result['msg'])

        if command == "PowerOn" or command == "PowerForceOff" or command == "PowerGracefulRestart" or command == "PowerGracefulShutdown":
            result = rf_utils.manage_system_power("/Actions/ComputerSystem.Reset", command)
        elif command == "GetBiosAttributes":
            result = rf_utils.get_bios_attributes("/Bios")
        elif command == "GetBiosBootOrder":
            result = rf_utils.get_bios_boot_order("/Bios", "/BootSources")
        elif command == "SetOneTimeBoot":
            result = rf_utils.set_one_time_boot_device(bootdevice, "/Bios")
        elif command == "SetBiosDefaultSettings":
            result = rf_utils.set_bios_default_settings("/Bios/Actions/Bios.ResetBios")
        elif command == "SetBiosAttributes":
            result = rf_utils.set_bios_attributes("/Bios/Settings", bios_attributes)
        elif command == "CreateBiosConfigJob":
            # execute only if we find a Managers resource
            result = rf_utils._find_managers_resource(rf_uri)
            if result['ret'] == False: module.fail_json(msg=result['msg'])
            result = rf_utils.create_bios_config_job("/Bios/Settings", "/Jobs")
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Update":
        # execute only if we find UpdateService resources
        result = rf_utils._find_updateservice_resource(rf_uri)
        if result['ret'] == False: module.fail_json(msg=result['msg'])

        if command == "GetFirmwareInventory":
            result = rf_utils.get_firmware_inventory()
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Manager":
        # execute only if we find a Manager service resource
        result = rf_utils._find_managers_resource(rf_uri)
        if result['ret'] == False: module.fail_json(msg=result['msg'])

        # The URIs being passed are hard-coded but could easily be built dynamically by
        # looking in resources Links["Oem"] and Actions["Oem"]["target"] under manager_uri.
        # Leaving here for reference only so it can be adapted for other OEMs.
        if command == "GracefulRestart":
            result = rf_utils.restart_manager_gracefully("/Actions/Manager.Reset")
        elif command == "GetAttributes":
            result = rf_utils.get_manager_attributes("/Attributes")
        elif command == "SetAttributes":
            result = rf_utils.set_manager_attributes("/Attributes", mgr_attributes)
        elif command == "SetDefaultSettings":
            result = rf_utils.set_manager_default_settings("/Actions/Oem/DellManager.ResetToDefaults")

        # Logs
        elif command == "ViewLogs":
            result = rf_utils.view_logs()
        elif command == "ClearLogs":
            result = rf_utils.clear_logs()
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    else:
        result = { 'ret': False, 'msg': 'Invalid Category'}

    # Return data back or fail with proper message
    if result['ret'] == True:
        del result['ret']		# Don't want to pass this back
        module.exit_json(result=result)
    else:
        module.fail_json(msg=result['msg'])

if __name__ == '__main__':
    main()
