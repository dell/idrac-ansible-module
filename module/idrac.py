#!/usr/bin/env python
# -*- coding: utf-8 -*-

# (c) 2017, Dell EMC Inc.
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
                    'version': '0.1'}

DOCUMENTATION = """
module: idrac
version_added: "2.3"
short_description: Manage Dell EMC hardware through iDRAC Redfish APIs
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
  idracip:
    required: true
    default: None
    description:
      - iDRAC IP address
  idracuser:
    required: false
    default: root
    description:
      - iDRAC user name used for authentication
  idracpswd:
    required: false
    default: calvin
    description:
      - iDRAC user passwore used for authentication
  userid:
    required: false
    default: None
    description:
      - ID of iDRAC user to add/delete/modify
  username:
    required: false
    default: None
    description:
      - name of iDRAC user to add/delete/modify
  userpswd:
    required: false
    default: None
    description:
      - password of iDRAC user to add/delete/modify
  userrole:
    required: false
    default: None
    description:
      - role of iDRAC user to add/delete/modify
  sharehost:
    required: false
    default: None
    description:
      - CIFS/SMB share hostname for managing SCP files
  sharename:
    required: false
    default: None
    description:
      - CIFS/SMB share name for managing SCP files
  shareuser:
    required: false
    default: None
    description:
      - CIFS/SMB share user for managing SCP files
  sharepswd:
    required: false
    default: None
    description:
      - CIFS/SMB share user password for managing SCP files
  bootdevice:
    required: false
    default: None
    description:
      - bootdevice when setting boot configuration
  bios_attributes:
    required: false
    default: None
    description:
      - dict where we specify BIOS attributes to set
  FWPath:
    required: false
    default: None
    description:
      - firmware binary path which is used to upload firmware
  Model:
    required: false
    default: None
    description:
      - system model name like R940, R740
  InstallOption:
    required: false
    choices: [ Now, NowAndReboot, NextReboot ]
    default: None
    description:
      - firmware installation option like Now or NextReboot

author: "jose.delarosa@dell.com"
"""

import os
import requests
import json
import re
import xml.etree.ElementTree as ET
from distutils.version import LooseVersion
from datetime import datetime
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from ansible.module_utils.basic import AnsibleModule

def send_get_request(idrac, uri):
    result = {}
    try:
        response = requests.get(uri, verify=False, auth=(idrac['user'], idrac['pswd']))
    except:
        raise			# Do we let module exit or should we return an error value?
    return response

def send_post_request(idrac, uri, pyld, hdrs,fileName=None):

    try:
        response = requests.post(uri, data=json.dumps(pyld), headers=hdrs,files=fileName,
                           verify=False, auth=(idrac['user'], idrac['pswd']))
    except:
        raise			# Do we let module exit or should we return an error value?
    return response

def send_patch_request(idrac, uri, pyld, hdrs):
    result = {}
    try:
        response = requests.patch(uri, data=json.dumps(pyld), headers=hdrs,
                           verify=False, auth=(idrac['user'], idrac['pswd']))
    except:
        raise			# Do we let module exit or should we return an error value?
    return response

def export_scp(IDRAC_INFO, SHARE_INFO, hostname, root_uri):
    result = {}
    # timestamp to add to SCP XML file name
    ts = str(datetime.strftime(datetime.now(), "_%Y%m%d_%H%M%S"))
    scp_uri = root_uri + "/Actions/Oem/EID_674_Manager.ExportSystemConfiguration"
    headers = {'content-type': 'application/json'}
    payload = { "ExportFormat" : "XML",
                "ShareParameters" : { "Target" : "ALL",
                     "ShareType" : "CIFS",
                     "IPAddress" : SHARE_INFO['host'],
                     "ShareName" : SHARE_INFO['name'],
                     "UserName"  : SHARE_INFO['user'],
                     "Password"  : SHARE_INFO['pswd'],
                     "FileName"  : "SCP_" + hostname + ts + ".xml"}
              }
    response = send_post_request(IDRAC_INFO, scp_uri, payload, headers)
    if response.status_code == 202:		# success
        result['ret'] = True
        # Getting Job ID, but not really doing anything with it
        data_dict = response.__dict__
        job_id_full = data_dict["headers"]["Location"]
        job_id = re.search("JID_.+", job_id_full).group()
    else:
        result = { 'ret': False, 'msg': "Status code %s" % response.status_code }
    return result

def get_stor_cont_info(IDRAC_INFO, root_uri, rf_uri):
    result = {}
    controllers_details = []

    # Get a list of all storage controllers and build respective URIs
    controller_list = []
    response = send_get_request(IDRAC_INFO, root_uri + rf_uri)
    if response.status_code == 200:             # success
        result['ret'] = True
        data = response.json()

        for controller in data[u'Members']:
            controller_list.append(controller[u'@odata.id'])

        for c in controller_list:
            uri = root_uri + c
            response = send_get_request(IDRAC_INFO, uri)
            if response.status_code == 200:             # success
                data = response.json()

                controller = {}
                controller['Name']   = data[u'Name']	# Name of storage controller
                controller['Health'] = data[u'Status'][u'Health']
                controllers_details.append(controller)
            else:
                result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
                return result		# no need to go through the whole loop

        result["entries"] = controllers_details
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def get_disk_info(IDRAC_INFO, root_uri, rf_uri):
    result = {}
    disks_details = []

    # Get a list of all storage controllers and build respective URIs
    controller_list = []
    response = send_get_request(IDRAC_INFO, root_uri + rf_uri)
    if response.status_code == 200:             # success
        result['ret'] = True
        data = response.json()

        for controller in data[u'Members']:
            controller_list.append(controller[u'@odata.id'])

        for c in controller_list:
            uri = root_uri + c
            response = send_get_request(IDRAC_INFO, uri)
            if response.status_code == 200:             # success
                data = response.json()

                for device in data[u'Devices']:
                    disk = {}
                    disk['Controller']   = data[u'Name']	# Name of storage controller
                    disk['Name']         = device[u'Name']
                    disk['Manufacturer'] = device[u'Manufacturer']
                    disk['Model']        = device[u'Model']
                    disk['State']        = device[u'Status'][u'State']
                    disk['Health']       = device[u'Status'][u'Health']
                    disks_details.append(disk)
            else:
                result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
                return result		# no need to go through the whole loop

        result["entries"] = disks_details
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def restart_idrac_gracefully(IDRAC_INFO, root_uri):
    result = {}
    uri = root_uri + "/Actions/Manager.Reset"
    headers = {'content-type': 'application/json'}
    payload = {'ResetType': 'GracefulRestart'}
    response = send_post_request(IDRAC_INFO, uri, payload, headers)
    if response.status_code == 204:		# success
        result['ret'] = True
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def manage_system_power(command, IDRAC_INFO, root_uri):
    result = {}
    headers = {'content-type': 'application/json'}
    uri = root_uri + "/Actions/ComputerSystem.Reset"

    if command == "PowerOn":
        payload = {'ResetType': 'On'}
        response = send_post_request(IDRAC_INFO, uri, payload, headers)

    elif command == "PowerOff":
        payload = {'ResetType': 'ForceOff'}
        response = send_post_request(IDRAC_INFO, uri, payload, headers)

    elif command == "GracefulRestart":
        payload = {'ResetType': 'GracefulRestart'}
        response = send_post_request(IDRAC_INFO, uri, payload, headers)

    elif command == "GracefulShutdown":
        payload = {'ResetType': 'GracefulShutdown'}
        response = send_post_request(IDRAC_INFO, uri, payload, headers)

    else:
        result = { 'ret': False, 'msg': 'Invalid Command'}

    if response.status_code == 204:		# success
        result['ret'] = True
    elif response.status_code == 400:
        result = { 'ret': False, 'msg': '14G only'}
    elif response.status_code == 405:
        result = { 'ret': False, 'msg': "Resource not supported" }
    elif response.status_code == 409:		# verify this
        result = { 'ret': False, 'msg': "Action already implemented" }
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def list_users(IDRAC_INFO, USER_INFO, root_uri, rf_uri):
    result = {}
    uri = root_uri + rf_uri + "/Accounts/"
    allusers = []
    allusers_details = []

    response = send_get_request(IDRAC_INFO, uri)
    if response.status_code == 200:		# success
        result['ret'] = True
        data = response.json()
        for users in data[u'Members']:
            allusers.append(users[u'@odata.id'])	# Here user_list[] are URIs

        # for each user, get details
        for uri in allusers:
            response = send_get_request(IDRAC_INFO, root_uri + uri)
            # check status_code again?
            data = response.json()
            if not data[u'UserName'] == "": # only care if name is not empty
                user = {}
                user['Id']       = data[u'Id']
                user['Name']     = data[u'Name']
                user['UserName'] = data[u'UserName']
                user['RoleId']   = data[u'RoleId']
                allusers_details.append(user)
            result["entries"] = allusers_details
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def manage_users(command, IDRAC_INFO, USER_INFO, root_uri, rf_uri):
    result = {}
    headers = {'content-type': 'application/json'}
    uri = root_uri + rf_uri + "/Accounts/" + USER_INFO['userid']

    if command == "AddUser":
        user    = {'UserName': USER_INFO['username']}
        pswd    = {'Password': USER_INFO['userpswd']}
        roleid  = {'RoleId': USER_INFO['userrole']}
        enabled = {'Enabled': True}
        for payload in user,pswd,roleid,enabled:
            response = send_patch_request(IDRAC_INFO, uri, payload, headers)
            if response.status_code == 200:		# success
                result['ret'] = True
            else:
                result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    elif command == "DisableUser":
        payload = {'Enabled': False}
        response = send_patch_request(IDRAC_INFO, uri, payload, headers)
        if response.status_code == 200:		# success
            result['ret'] = True
        else:
            result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    elif command == "EnableUser":
        payload = {'Enabled': True}
        response = send_patch_request(IDRAC_INFO, uri, payload, headers)
        if response.status_code == 200:		# success
            result['ret'] = True
        else:
            result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    elif command == "UpdateUserRole":
        payload = {'RoleId': USER_INFO['userrole']}
        response = send_patch_request(IDRAC_INFO, uri, payload, headers)
        if response.status_code == 200:		# success
            result['ret'] = True
        else:
            result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    elif command == "UpdateUserPassword":
        payload = {'Password': USER_INFO['userpswd']}
        response = send_patch_request(IDRAC_INFO, uri, payload, headers)
        if response.status_code == 200:		# success
            result['ret'] = True
        else:
            result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    elif command == "DeleteUser":
        payload = {'UserName': ""}
        response = send_patch_request(IDRAC_INFO, uri, payload, headers)
        if response.status_code == 200:		# success
            result['ret'] = True
        else:
            result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    else:
        result = { 'ret': False, 'msg': "Invalid Command" }

    return result

def get_se_logs(IDRAC_INFO, root_uri):
    # System Event logs
    result = {}
    allentries = []
    response = send_get_request(IDRAC_INFO, root_uri + "/Logs/Sel")
    if response.status_code == 200:		# success
        result['ret'] = True
        data = response.json()
        for logEntry in data[u'Members']:
            # I only extract some fields
            entry = {}
            entry['Name']    = logEntry[u'Name']
            entry['Created'] = logEntry[u'Created']
            entry['Message'] = logEntry[u'Message']
            allentries.append(entry)
        result["entries"] = allentries
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    # This looks like: result{allentries[entry{}]}
    return result

def get_lc_logs(IDRAC_INFO, root_uri):
    # Lifecycle Controller logs
    result = {}
    allentries = []
    response = send_get_request(IDRAC_INFO, root_uri + "/Logs/Lclog")
    if response.status_code == 200:		# success
        result['ret'] = True
        data = response.json()
        for logEntry in data[u'Members']:
            # I only extract some fields
            entry = {}
            entry['Name']     = logEntry[u'Name']
            entry['Created']  = logEntry[u'Created']
            entry['Message']  = logEntry[u'Message']
            entry['Severity'] = logEntry[u'Severity']
            allentries.append(entry)
        result["entries"] = allentries
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    # This looks like: result{allentries[entry{}]}
    return result

def get_firmware_inventory(IDRAC_INFO, root_uri, rf_uri):
    result = {}
    devices = []

    response = send_get_request(IDRAC_INFO, root_uri + rf_uri)
    if response.status_code == 200:		# success
        result['ret'] = True
        data = response.json()
        for device in data[u'Members']:
            d = device[u'@odata.id']
            d = d.replace(rf_uri, "")	# leave just device name
            if "Installed" in d:
                # Get details for each device that is relevant
                uri = root_uri + rf_uri + d
                response = send_get_request(IDRAC_INFO, uri)
                if response.status_code == 200:	# success
                    data = response.json()
                    result[data[u'Name']] = data[u'Version']

    # PropertyValueTypeError
    elif response.status_code == 400:
        result = { 'ret': False, 'msg': '14G only'}
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    return result

def compare_firmware(IDRAC_INFO, root_uri, catalog_file, model):
    fw = []
    fw_list = {'ret':True, 'Firmwares':[]}

    response = send_get_request(IDRAC_INFO, root_uri + '/redfish/v1/UpdateService/FirmwareInventory/')
    if response.status_code == 200:
        data = response.json()

        for i in data['Members']:
            if 'Installed' in i['@odata.id']:
                fw.append(i['@odata.id'])

        # read catalog file
        tree = ET.parse(catalog_file)
        root = tree.getroot()
        for inv in fw:
            ver = inv.split('-')[1]
            version = '0'
            path = ""
            for i in root.findall('.//Category/..'):
                        for m in i.findall('.//SupportedDevices/Device'):
                            if m.attrib['componentID'] == ver:
                                for nx in i.findall('.//SupportedSystems/Brand/Model/Display'):
                                    if nx.text == model:
                                        if LooseVersion(i.attrib['vendorVersion']) > LooseVersion(version):
                                            version = i.attrib['vendorVersion']
                                            path = i.attrib['path']

	    if path != "":
		fw_list['Firmwares'].append({ 'curr':'%s' % os.path.basename(inv).replace('Installed-%s-'%ver,''), 'latest':'%s' % version, 'path':'%s' % path })
    else:
        fw_list['ret'] = False
    return fw_list

def upload_firmware(IDRAC_INFO, root_uri, FWPath):
    result = {}
    response = send_get_request(IDRAC_INFO, root_uri + '/redfish/v1/UpdateService/FirmwareInventory/')
    if response.status_code == 200:
        ETag = response.headers['ETag']
    else:
        result = { 'ret': False, 'msg': 'Failed to get update service etag %s' % str(root_uri)}
        return result

    files = {'file': (os.path.basename(FWPath), open(FWPath, 'rb'), 'multipart/form-data')}
    headers = {"if-match": ETag}
    url = root_uri + '/redfish/v1/UpdateService/FirmwareInventory'

    # Calling POST directly rather than use send_post_request() - look into it?
    response = requests.post(url, files=files, auth=(IDRAC_INFO['user'], IDRAC_INFO['pswd']), headers=headers, verify=False)
    if response.status_code == 201:
        result = { 'ret': True, 'msg': 'Firmare uploaded successfully', 'Version': '%s' % str(response.json()['Version']), 'Location':'%s' % response.headers['Location']}

    elif response.status_code == 400:
        result = { 'ret': False, 'msg': '14G only'}

    else:
        result = { 'ret': False, 'msg': 'Failed to upload firmware image %s' % str(response.__dict__)}
    return result

def schedule_firmware_update(IDRAC_INFO, root_uri, InstallOption):
    fw = []
    response = send_get_request(IDRAC_INFO, root_uri + '/redfish/v1/UpdateService/FirmwareInventory/')
    if response.status_code == 200:
        data = response.json()
        for i in data['Members']:
            if 'Available' in i['@odata.id']:
                fw.append(i['@odata.id'])

    url = root_uri + '/redfish/v1/UpdateService/Actions/Oem/DellUpdateService.Install'
    payload = { "SoftwareIdentityURIs":fw, "InstallUpon":"InstallOption "}
    headers = {'content-type': 'application/json'}
    response = send_post_request(IDRAC_INFO, url, payload, headers)
    if response.status_code == 202:
        result = { 'ret': True, 'msg': 'firmware install job accepted ', 'Location':'%s' % str(response.json()) }

    elif response.status_code == 400:
        result = { 'ret': False, 'msg': '14G only'}
    else:
        result = { 'ret': True, 'msg': 'failed to schedule firmware install job', 'code':'%s' % str(response.__dict__)}
    return result

def get_bios_attributes(IDRAC_INFO, root_uri):
    result = {}
    response = send_get_request(IDRAC_INFO, root_uri + "/Bios")
    if response.status_code == 200:		# success
        data = response.json()
        for attribute in data[u'Attributes'].items():
            result[attribute[0]] = attribute[1]
        result['ret'] = True
    # PropertyValueTypeError
    elif response.status_code == 400:
        result = { 'ret': False, 'msg': '14G only'}
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    return result

def get_bios_boot_order(IDRAC_INFO, root_uri):
    # Get boot mode first as it will determine what attribute to read
    result = {}
    response = send_get_request(IDRAC_INFO, root_uri + "/Bios")
    if response.status_code == 200:		# success
        result['ret'] = True
        data = response.json()
        boot_mode = data[u'Attributes']["BootMode"]
        response = send_get_request(IDRAC_INFO, root_uri + "/BootSources")
        if response.status_code == 200:		# success
            data = response.json()
            if boot_mode == "Uefi":
                boot_seq = "UefiBootSeq"
            else:
                boot_seq = "BootSeq"
            boot_devices = data[u'Attributes'][boot_seq]
            for b in boot_devices:
                result["device%s" % b[u'Index']] = b[u'Name']
    # PropertyValueTypeError
    elif response.status_code == 400:
        result = { 'ret': False, 'msg': '14G only'}
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    return result

def get_fans_stats(IDRAC_INFO, root_uri):
    result = {}
    fan_details = []
    response = send_get_request(IDRAC_INFO, root_uri)
    if response.status_code == 200:             # success
        result['ret'] = True
        data = response.json()

        for device in data[u'Fans']:
            # There is more information available but this is most important
            fan = {}
            fan['Name']   = device[u'FanName']
            fan['RPMs']   = device[u'Reading']
            fan['State']  = device[u'Status'][u'State']
            fan['Health'] = device[u'Status'][u'Health']
            fan_details.append(fan)
        result["entries"] = fan_details

    elif response.status_code == 400:
        result = { 'ret': False, 'msg': '14G only'}
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }

    return result

def set_bios_default_settings(IDRAC_INFO, root_uri):
    result = {}
    payload = {}
    headers = {'content-type': 'application/json'}
    response = send_post_request(IDRAC_INFO, root_uri, payload, headers)
    if response.status_code == 200:		# success
        result = { 'ret': True, 'msg': 'SetBiosDefaultSettings completed'}
    elif response.status_code == 405:
        result = { 'ret': False, 'msg': "Resource not supported" }
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def set_one_time_boot_device(IDRAC_INFO, bootdevice, root_uri):
    result = {}
    payload = {"Boot": {"BootSourceOverrideTarget": bootdevice}}
    headers = {'content-type': 'application/json'}
    response = send_patch_request(IDRAC_INFO, root_uri, payload, headers)
    if response.status_code == 200:		# success
        result = { 'ret': True, 'msg': 'SetOneTimeBoot completed'}
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def set_idrac_default_settings(IDRAC_INFO, root_uri):
    result = {}
    payload = {"ResetType": "All"}
    headers = {'content-type': 'application/json'}
    response = send_post_request(IDRAC_INFO, root_uri, payload, headers)
    if response.status_code == 200:		# success
        result = { 'ret': True, 'msg': 'SetIdracDefaultSettings completed'}
    elif response.status_code == 405:
        result = { 'ret': False, 'msg': "Resource not supported" }
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def set_bios_attributes(IDRAC_INFO, root_uri, bios_attributes):
    result = {}
    bios_attributes=bios_attributes.replace("'","\"")
    payload = {"Attributes": json.loads(bios_attributes) }
    headers = {'content-type': 'application/json'}
    response = send_patch_request(IDRAC_INFO, root_uri, payload, headers)
    if response.status_code == 200:
        result = { 'ret': True, 'msg': 'BIOS Attributes set as pending values'}
    elif response.status_code == 405:
        result = { 'ret': False, 'msg': "Resource not supported" }
    else:
        pp = response.json()
        result = { 'ret': False, 'msg': "Error code %s" % str(pp) }
    return result

def create_bios_config_job (IDRAC_INFO, url):
    payload = {"TargetSettingsURI":"/redfish/v1/Systems/System.Embedded.1/Bios/Settings", "RebootJobType":"PowerCycle"}
    headers = {'content-type': 'application/json'}
    response = send_post_request(IDRAC_INFO, url, payload, headers)
    if response.status_code == 200:
        result = { 'ret': True, 'msg': 'Config job created'}
    else:
        pp = response.json()
        result = { 'ret': False, 'msg': "Error code %s" % str(pp) }
    return result

def get_cpu_inventory(IDRAC_INFO, root_uri, rf_uri):
    result = {}
    cpu_details = []

    # Get a list of all CPUs and build respective URIs
    cpu_list = []
    response = send_get_request(IDRAC_INFO, root_uri + rf_uri)
    if response.status_code == 200:		# success
        result['ret'] = True
        data = response.json()

        for cpu in data[u'Members']:
            cpu_list.append(cpu[u'@odata.id'])

        for c in cpu_list:
            uri = root_uri + c
            response = send_get_request(IDRAC_INFO, uri)
            if response.status_code == 200:             # success
                data = response.json()
                cpu = {}
                cpu['Name']         = data[u'Id']
                cpu['Manufacturer'] = data[u'Manufacturer']
                cpu['Model']        = data[u'Model']
                cpu['MaxSpeedMHz']  = data[u'MaxSpeedMHz']
                cpu['TotalCores']   = data[u'TotalCores']
                cpu['TotalThreads'] = data[u'TotalThreads']
                cpu['State']        = data[u'Status'][u'State']
                cpu['Health']       = data[u'Status'][u'Health']
                cpu_details.append(cpu)

            else:
                result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
                return result           # no need to go through the whole loop

        result["entries"] = cpu_details
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def get_nic_information(IDRAC_INFO, root_uri, rf_uri):
    result = {}
    nic_details = []

    # Get a list of all network controllers and build respective URIs
    nic_list = []
    response = send_get_request(IDRAC_INFO, root_uri + rf_uri)
    if response.status_code == 200:		# success
        result['ret'] = True
        data = response.json()

        for nic in data[u'Members']:
            nic_list.append(nic[u'@odata.id'])

        for n in nic_list:
            uri = root_uri + n
            response = send_get_request(IDRAC_INFO, uri)
            if response.status_code == 200:             # success
                data = response.json()
                nic = {}
                nic['Name']  = data[u'Name']
                nic['FQDN']  = data[u'FQDN']
                for d in data[u'IPv4Addresses']:
                    nic['IPv4']       = d[u'Address']
                    nic['Gateway']    = d[u'GateWay']
                    nic['SubnetMask'] = d[u'SubnetMask']
                for d in data[u'IPv6Addresses']:
                    nic['IPv6']   = d[u'Address']
                for d in data[u'NameServers']:
                    nic['NameServers'] = d
                nic['MAC']        = data[u'PermanentMACAddress']
                nic['Speed']      = data[u'SpeedMbps']
                nic['MTU']        = data[u'MTUSize']
                nic['Autoneg']    = data[u'AutoNeg']
                nic['State']      = data[u'Status'][u'State']
                nic['Health']     = data[u'Status'][u'Health']
                nic_details.append(nic)

            else:
                result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
                return result           # no need to go through the whole loop

        result["entries"] = nic_details
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def get_psu_inventory(IDRAC_INFO, root_uri, rf_uri):
    result = {}
    psu_details = []

    # Get a list of all PSUs and build respective URIs
    psu_list = []
    response = send_get_request(IDRAC_INFO, root_uri + rf_uri)
    if response.status_code == 200:		# success
        result['ret'] = True
        data = response.json()

        for psu in data[u'Links'][u'PoweredBy']:
            psu_list.append(psu[u'@odata.id'])

        for p in psu_list:
            uri = root_uri + p
            response = send_get_request(IDRAC_INFO, uri)
            if response.status_code == 200:             # success
                data = response.json()

                psu = {}
                psu['Name']            = data[u'Name']
                psu['Model']           = data[u'Model']
                psu['SerialNumber']    = data[u'SerialNumber']
                psu['PartNumber']      = data[u'PartNumber']
                # Only supported in 14G, so commenting out for now
                #psu['Manufacturer']    = data[u'Manufacturer']
                psu['FirmwareVersion'] = data[u'FirmwareVersion']
                psu['PowerCapacityWatts'] = data[u'PowerCapacityWatts']
                psu['PowerSupplyType'] = data[u'PowerSupplyType']
                psu['Status']          = data[u'Status'][u'State']
                psu['Health']          = data[u'Status'][u'Health']
                psu_details.append(psu)

            else:
                result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
                return result           # no need to go through the whole loop

        result["entries"] = psu_details
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def get_system_inventory(IDRAC_INFO, root_uri):
    result = {}
    response = send_get_request(IDRAC_INFO, root_uri)
    if response.status_code == 200:		# success
        result['ret'] = True
        data = response.json()

        # There could be more information to extract
        result['Status']       = data[u'Status'][u'Health']
        result['HostName']     = data[u'HostName']
        result['PowerState']   = data[u'PowerState']
        result['Model']        = data[u'Model']
        result['Manufacturer'] = data[u'Manufacturer']
        result['PartNumber']   = data[u'PartNumber']
        result['SystemType']   = data[u'SystemType']
        result['AssetTag']     = data[u'AssetTag']
        result['ServiceTag']   = data[u'SKU']
        result['SerialNumber'] = data[u'SerialNumber']
        result['BiosVersion']  = data[u'BiosVersion']
        result['MemoryTotal']  = data[u'MemorySummary'][u'TotalSystemMemoryGiB']
        result['MemoryHealth'] = data[u'MemorySummary'][u'Status'][u'Health']
        result['CpuCount']     = data[u'ProcessorSummary'][u'Count']
        result['CpuModel']     = data[u'ProcessorSummary'][u'Model']
        result['CpuHealth']    = data[u'ProcessorSummary'][u'Status'][u'Health']

        datadict = data[u'Boot']
        if 'BootSourceOverrideMode' in datadict.keys():
            result['BootSourceOverrideMode'] = data[u'Boot'][u'BootSourceOverrideMode']
        else:
            result['BootSourceOverrideMode'] = "14G only"

        if 'TrustedModules' in data:
            for d in data[u'TrustedModules']:
                result['TPMInterfaceType'] = d[u'InterfaceType']
                result['TPMStatus']        = d[u'Status'][u'State']
        else:
            result['TPMInterfaceType'] = "14G only" 
            result['TPMStatus']        = "14G only" 
    else:
        result = { 'ret': False, 'msg': "Error code %s" % response.status_code }
    return result

def main():
    result = {}
    module = AnsibleModule(
        argument_spec = dict(
            category   = dict(required=True, type='str', default=None),
            command    = dict(required=True, type='str', default=None),
            idracip    = dict(required=True, type='str', default=None),
            idracuser  = dict(required=False, type='str', default='root'),
            idracpswd  = dict(required=False, type='str', default='calvin'),
            userid     = dict(required=False, type='str', default=None),
            username   = dict(required=False, type='str', default=None),
            userpswd   = dict(required=False, type='str', default=None),
            userrole   = dict(required=False, type='str', default=None),
            hostname   = dict(required=False, type='str', default=None),
            sharehost  = dict(required=False, type='str', default=None),
            sharename  = dict(required=False, type='str', default=None),
            shareuser  = dict(required=False, type='str', default=None),
            sharepswd  = dict(required=False, type='str', default=None),
            bootdevice = dict(required=False, type='str', default=None),
            bios_attributes = dict(required=False, type='str', default=None),
	    FWPath     = dict(required=False, type='str', default=None),
	    Model      = dict(required=False, type='str', default=None),
	    InstallOption = dict(required=False, type='str', default=None, choices=['Now', 'NowAndReboot', 'NextReboot']),
        ),
        supports_check_mode=False
    )

    params = module.params
    category   = params['category']
    command    = params['command']
    hostname   = params['hostname']
    bootdevice = params['bootdevice']

    # Disable insecure-certificate-warning message
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    IDRAC_INFO = { 'ip'   : params['idracip'],
                   'user' : params['idracuser'],
                   'pswd' : params['idracpswd']
                 }
    SHARE_INFO = { 'host' : params['sharehost'],
                   'name' : params['sharename'],
                   'user' : params['shareuser'],
                   'pswd' : params['sharepswd']
                 }
    USER_INFO = { 'userid'   : params['userid'],
                  'username' : params['username'],
                  'userpswd' : params['userpswd'],
                  'userrole' : params['userrole']
                 }

    # Build initial URI
    root_uri = "https://" + params['idracip']

    # Execute based on what we want. Notice that some rf_uri values have an
    # ending slash ('/') and other don't. It's all by design and depends on
    # how the URI is used in each function.
    if category == "Inventory":
        rf_uri = "/redfish/v1/Systems/System.Embedded.1/"
        if command == "GetSystemInventory":
            result = get_system_inventory(IDRAC_INFO, root_uri + rf_uri)
        elif command == "GetPSUInventory":
            result = get_psu_inventory(IDRAC_INFO, root_uri, rf_uri)
        elif command == "GetCPUInventory":
            rf_uri = "/redfish/v1/Systems/System.Embedded.1/Processors"
            result = get_cpu_inventory(IDRAC_INFO, root_uri, rf_uri)
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Firmware":
        rf_uri = "/redfish/v1/UpdateService/FirmwareInventory/"
        if command == "GetInventory":
           result = get_firmware_inventory(IDRAC_INFO, root_uri, rf_uri)
	elif command == "UploadFirmware":
            result = upload_firmware(IDRAC_INFO, root_uri, params['FWPath'])
	elif command == "FirmwareCompare":
            result = compare_firmware(IDRAC_INFO, root_uri, "/tmp/Catalog", params['Model'])
        elif command == "InstallFirmware":
            result = schedule_firmware_update(IDRAC_INFO, root_uri, params['InstallOption'])
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Logs":
        rf_uri = "/redfish/v1/Managers/iDRAC.Embedded.1"
        if command == "GetSeLogs":
            result = get_se_logs(IDRAC_INFO, root_uri + rf_uri)
        elif command == "GetLcLogs":
            result = get_lc_logs(IDRAC_INFO, root_uri + rf_uri)
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Users":
        rf_uri = "/redfish/v1/Managers/iDRAC.Embedded.1"
        if command == "ListUsers":
            result = list_users(IDRAC_INFO, USER_INFO, root_uri, rf_uri)
        else:
            result = manage_users(command, IDRAC_INFO, USER_INFO, root_uri, rf_uri)

    elif category == "SystemPower":
        rf_uri = "/redfish/v1/Systems/System.Embedded.1"
        result = manage_system_power(command, IDRAC_INFO, root_uri + rf_uri)

    elif category == "Network":
        if command == "GetNICInfo":
            rf_uri = "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/"
            result = get_nic_information(IDRAC_INFO, root_uri, rf_uri)
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Storage":
        rf_uri = "/redfish/v1/Systems/System.Embedded.1/Storage/Controllers/"
        if command == "GetControllerInfo":
            result = get_stor_cont_info(IDRAC_INFO, root_uri, rf_uri)
        elif command == "GetDiskInfo":
            result = get_disk_info(IDRAC_INFO, root_uri, rf_uri)
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "SCP":
        rf_uri = "/redfish/v1/Managers/iDRAC.Embedded.1"
        if command == "ExportSCP":
            result = export_scp(IDRAC_INFO, SHARE_INFO, hostname, root_uri + rf_uri)
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Cooling":
        rf_uri = "/redfish/v1/Chassis/System.Embedded.1/Thermal"
        if command == "GetFanStats":
            result = get_fans_stats(IDRAC_INFO, root_uri + rf_uri)
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Bios":
        rf_uri = "/redfish/v1/Systems/System.Embedded.1"
        if command == "GetAttributes":
            result = get_bios_attributes(IDRAC_INFO, root_uri + rf_uri)
        elif command == "GetBootOrder":
            result = get_bios_boot_order(IDRAC_INFO, root_uri + rf_uri)
        elif command == "SetOneTimeBoot":
            result = set_one_time_boot_device(IDRAC_INFO, bootdevice, root_uri + rf_uri)
        elif command == "SetDefaultSettings":
            rf_uri = "/redfish/v1/Systems/System.Embedded.1/Bios/Actions/Bios.ResetBios/"
            result = set_bios_default_settings(IDRAC_INFO, root_uri + rf_uri)
        elif command == "SetAttributes":
	    rf_uri = '/redfish/v1/Systems/System.Embedded.1/Bios/Settings'
	    result = set_bios_attributes(IDRAC_INFO, root_uri + rf_uri, params['bios_attributes'])
        elif command == "ConfigJob":
            rf_uri = '/redfish/v1/Managers/iDRAC.Embedded.1/Jobs'
            result = create_bios_config_job(IDRAC_INFO, root_uri + rf_uri)
        else:
            result = { 'ret': False, 'msg': 'Invalid Command'}

    elif category == "Idrac":
        if command == "SetDefaultSettings":
            rf_uri = "/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Oem/DellManager.ResetToDefaults"
            result = set_idrac_default_settings(IDRAC_INFO, root_uri + rf_uri)
        elif command == "IdracGracefulRestart":
            rf_uri = "/redfish/v1/Managers/iDRAC.Embedded.1"
            result = restart_idrac_gracefully(IDRAC_INFO, root_uri + rf_uri)
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
