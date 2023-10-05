"""
Copyright (c) 2023 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

import json
import logging
import os
import sys
from time import sleep

import requests
import yaml
from dotenv import load_dotenv
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.exceptions import ConnectTimeout
from rich.console import Console
from rich.logging import RichHandler
from schema import Schema, SchemaError

console = Console()
load_dotenv()
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

SDWAN_USER = os.getenv("SDWAN_USER")
SDWAN_PASS = os.getenv("SDWAN_PASS")
SDWAN_URL = os.getenv("SDWAN_URL")
UPS_USER = os.getenv("UPS_USER")
UPS_PASS = os.getenv("UPS_PASS")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

FORMAT = "%(message)s"
logging.basicConfig(
    level=LOG_LEVEL, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

log = logging.getLogger("rich")

AUTH_URL = f"{SDWAN_URL}/j_security_check"
AUTH_BODY = f"j_username={SDWAN_USER}&j_password={SDWAN_PASS}"

CSRF_URL = f"{SDWAN_URL}/dataservice/client/token"

FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}
JSON_HEADERS = {"Content-Type": "application/json"}

APPRS_URL = f"{SDWAN_URL}/dataservice/device/app-route/statistics"

BFDSTATE_URL = f"{SDWAN_URL}/dataservice/device/bfd/state/device"

CONFIG_SCHEMA = Schema(
    {
        "trigger": {"interval": int, "count": int},
        "sites": {int: {"color": str, "ups": str, "outlet": int}},
    }
)

HTTPTIMEOUT = 5


def loadConfig() -> None:
    """
    Load configuration file
    """
    log.info("Loading config file...")
    with open("./config.yaml", "r") as file:
        with console.status("Processing..."):
            config = yaml.safe_load(file)
            try:
                CONFIG_SCHEMA.validate(config)
                log.info("Config loaded!")
                return config
            except SchemaError as e:
                log.fatal("Failed to validate config.yaml. Error:")
                log.fatal(e)
                sys.exit(1)


class sdwan:
    def __init__(self, config: dict):
        self.sites = config["sites"]
        self.setup()
        self.session = requests.Session()
        self.getAuthToken()
        self.getDevices()
        self.startMonitor()

    def startMonitor(self):
        """
        Run primary monitoring routine
        """
        while True:
            log.info("Beginning health checks...")
            for site in self.sites:
                for device in self.sites[site]["devices"]:
                    # BFD Monitor
                    log.debug(f"Checking device {device} at site ID {site}")
                    self.getBFDState(site, device, self.sites[site]["color"])
                    if all(x == "DOWN" for x in self.sites[site]["bfd"]):
                        ups = EatonUPS(self.sites[site]["ups"])
                        ups.powerCycle(self.sites[site]["outlet"])
                        # Reset monitoring
                        self.sites[site]["bfd"] = [""] * config["trigger"]["count"]
                count = len([x for x in self.sites[site]["bfd"] if x == "DOWN"])
                log.info(
                    f"Site {site} status: {count}/{config['trigger']['count']} probes reported down"
                )
            log.info("Health checks complete.")
            sleep(config["trigger"]["interval"])

    def setup(self):
        """
        Set up structure of local data store
        """
        for site in self.sites:
            self.sites[site]["devices"] = []
            self.sites[site]["bfd"] = [""] * config["trigger"]["count"]

    def getAuthToken(self):
        """
        Retrieve authentication token from vManage
        """
        log.info(f"Attempting to authenticate to: {SDWAN_URL}")
        try:
            response = self.session.post(
                url=AUTH_URL,
                headers=FORM_HEADERS,
                data=AUTH_BODY,
                verify=False,
                timeout=HTTPTIMEOUT,
            )
        except ConnectTimeout:
            log.fatal("Timed out connecting to vManage!")
            sys.exit(1)
        if response.status_code == 200:
            for cookie in response.cookies:
                if cookie.name == "JSESSIONID":
                    log.info("Got authentication token!")
                    return
        else:
            log.fatal(f"Failed to authenticate. Status code: {response.status_code}")
            sys.exit(1)

    def getDevices(self):
        """
        Collect data on devices based on site IDs in config file
        """
        controllers = ["vmanage", "vbond", "vsmart"]
        site_list = [int(siteid) for siteid in self.sites]
        log.info("Collecting device info...")
        response = self.session.get(
            f"{SDWAN_URL}/dataservice/device",
            headers=JSON_HEADERS,
            verify=False,
            timeout=5,
        )
        if response.status_code == 200:
            devices = json.loads(response.text)["data"]
            for device in devices:
                site_id = int(device["site-id"])
                # Skip controllers
                if device["personality"] in controllers:
                    log.debug(f"Skipping controller: {device['personality']}")
                    continue
                # Skip devices that are not in config
                if site_id not in site_list:
                    log.debug(f"Skip device with Site ID: {site_id}")
                    continue
                # Skip unreachable devices
                if device["reachability"] != "reachable":
                    log.debug(f"Skipping unreachable device: {device['system-ip']}")
                    continue
                # Otherwise, add device to monitoring
                log.debug(f"Adding device: {device['system-ip']}")
                self.sites[site_id]["devices"].append(device["system-ip"])
            log.info("Done!")
        else:
            log.error("Failed to collect device info.")

    def getBFDState(self, site, device, color):
        """
        Check BFD state for a given device ID & color
        """
        url = BFDSTATE_URL + f"?deviceId={device}&local-color={color}"
        response = self.session.get(
            url, headers=JSON_HEADERS, verify=False, timeout=HTTPTIMEOUT
        )
        if response.status_code == 200:
            data = json.loads(response.text)["data"]
            # Remove oldest entry
            self.sites[site]["bfd"] = self.sites[site]["bfd"][:-1]
            # If all BFD probes for this color are down, mark last status as down
            if all([x["state"] == "down" for x in data if x["local-color"] == color]):
                self.sites[site]["bfd"].insert(0, "DOWN")
            elif all([x["state"] == "up" for x in data if x["local-color"] == color]):
                self.sites[site]["bfd"].insert(0, "UP")
            else:
                self.sites[site]["bfd"].insert(0, "PARTIAL")
        else:
            log.warn(f"Failed to query BFD state for {device} / {color}")
            self.sites[site]["bfd"].insert(0, "UNKNOWN")


class EatonUPS:
    def __init__(self, ip: str):
        self.ups_ip = ip
        self.session = requests.Session()
        self.getAuthToken()

    def getAuthToken(self):
        """
        Authenticate to Eaton UPS & retrieve authorization header
        """
        log.info(f"Connecting to UPS at: {self.ups_ip}")
        url = f"https://{self.ups_ip}/rest/mbdetnrs/1.0/oauth2/token"
        headers = {"Content-Type": "application/json"}
        auth_data = {
            "username": UPS_USER,
            "password": UPS_PASS,
            "grant_type": "password",
            "scope": "GUIAccess",
        }
        try:
            response = self.session.post(
                url, headers=headers, json=auth_data, verify=False, timeout=HTTPTIMEOUT
            )
        except requests.ConnectTimeout:
            log.error("Failed to connect to UPS. Connection timeout.")
            self.session = False
            return
        if response.status_code == 200:
            token = json.loads(response.text)["access_token"]
            self.auth_header = {"Authorization": f"Bearer {token}"}
            log.info("Got Auth token!")
        else:
            log.warn("Failed to connect / authenticate to UPS")

    def getOutletStatus(self) -> bool:
        """
        Get status of UPS outlet
        """
        log.info(f"Checking status of outlet {self.outlet} on UPS at {self.ups_ip}")

        url = f"https://{self.ups_ip}/rest/mbdetnrs/1.0/powerDistributions/1/outlets/{self.outlet}"
        response = self.session.get(
            url, headers=self.auth_header, verify=False, timeout=HTTPTIMEOUT
        )
        if response.status_code == 200:
            state = json.loads(response.text)["status"]["switchedOn"]
            if state:
                log.info("Outlet is currently ON")
            if not state:
                log.info("Outlet is currently OFF")
            return state
        else:
            log.warn("Failed to get outlet status")

    def switchOutlet(self, operation: str):
        """
        Switch outlet on or off
        """
        log.info(f"Attempting to switch outlet {self.outlet} to state: {operation}")
        url = f"https://{self.ups_ip}/rest/mbdetnrs/1.0/powerDistributions/1/outlets/{self.outlet}/actions/switch{operation}"
        response = self.session.post(
            url, headers=self.auth_header, verify=False, timeout=HTTPTIMEOUT
        )
        if response.status_code == 200:
            log.info("Action successful!")
        else:
            log.warn("Failed to modify outlet state")

    def powerCycle(self, outlet: int):
        """
        Switch outlet on & off
        """
        if not self.session:
            return
        self.outlet = outlet
        log.info(
            f"Beginning power cycle operation for outlet {self.outlet} on UPS {self.ups_ip}"
        )
        # Check current status before turning outlet off
        state = self.getOutletStatus()
        if state:
            self.switchOutlet("Off")

        count = 0
        while True:
            count += 1
            if count > 3:
                log.error("Not able to complete operation.")
                break
            # Allow a moment before trying to switch port back on
            log.info("Waiting...")
            sleep(5)
            state = self.getOutletStatus()
            # If outlet status is off, flip back on
            if not state:
                self.switchOutlet("On")
                sleep(2)
                state = self.getOutletStatus()
                # If outlet is not on yet, wait & try again
                if not state:
                    continue
            # If outlet is on, break loop
            if state:
                break


if __name__ == "__main__":
    config = loadConfig()
    try:
        sdwan(config)
    except KeyboardInterrupt:
        console.print("[red]Received Ctrl-C. Quitting...")
