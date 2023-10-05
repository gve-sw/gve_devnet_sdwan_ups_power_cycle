# Cisco SD-WAN - UPS Outlet Power Cycle

This code repository provides an example of how to power cycle outlets on an Eaton UPS based on Cisco SD-WAN circuit issues. The intent is to reboot an internet modem that may be plugged into the Eaton UPS, and attempt to automatically resolve connectivity issues.

At a high level, this script will:

- Connect to Cisco vManage
- Monitor locations defined in the script configuration file
- If all BFD sessions on a specified link are down
  - Issue REST API call to Eaton UPS to power cycle an outlet

For the intended purpose of this code, it was assumed that the customer has a second path to the remote site location in order to ensure the script can access the UPS REST API.

## Contacts

- Matt Schmitz (<mattsc@cisco.com>)

## Solution Components

- Cisco Viptela SD-WAN
- Eaton 9PX1500 with Network M2 card

## Installation/Configuration

### **Step 1 - Clone repo:**

```bash
git clone <repo_url>
```

### **Step 2 - Install required dependancies:**

```bash
pip install -r requirements.txt
```

### **Step 3 - Provide SD-WAN & UPS Credentials**

In order for the script to access vManage & the Eaton UPS, login credentials must be provided via environment variables.

Variables are listed below, and also provided in an example file (`example.env`). This file can be modified & re-named to `.env` - and the script will automatically load the required values.

```bash
SDWAN_USER=
SDWAN_PASS=
SDWAN_URL=
UPS_USER=
UPS_PASS=
```

### **Step 4 - Specify locations to monitor**

Next, there is some configuration for which locations to monitor & trigger conditions. Please reference the example snippet below.

```yaml
trigger:
  interval: 60
  count: 5
sites:
  100:
    color: public-internet
    ups: 10.10.10.10
    outlet: 2
  200:
    color: biz-internet
    ups: 20.20.20.20
    outlet: 2
```

Trigger conditions are listed under the `trigger` key.

- `interval` specifies how frequently the script runs, in seconds.
- `count` specifies how many bad probes must be detected before issuing the power cycle command to the UPS

In the example above, the script would poll vManage every 60 seconds - and invoke the power cycle after 5 missed BFD probes.

> Note: Due to the way the SD-WAN system works, BFD probe reporting via API is similar to what is on-device. Accuracy of this script will depend on device settings for `bfd app-route poll-interval`. Current BFD status on the device is only updated once per poll-interval - so this must match the script's configuration for query interval. For example, if we need the script to check status every 1 minute, then the device must be set to report BFD state on a 1 minute poll interval.

For the `sites` key, we can define each site by a site ID & the script will collect the WAN edge devices from that location to monitor. Then, for each site ID:

- `color` specifies which transport color needs to be monitored
- `ups` specifies the IP address of the Eaton UPS at that location
- `outlet` specifies which outlet to power cycle on a down event

> Note: Eaton UPS outlet ID provided to the script may not match the outlet group ID in the web UI. For the device used during development of this script, Outlet group 1 was mapped on the UPS to outlet ID #2. Current outlet IDs & assignments can be found using the [Get Outlets](https://documenter.getpostman.com/view/7058770/S1EQTJ3z#41e1b68e-3f67-4207-9f0d-3f989a094cfd) API calls.

## Usage

### Running locally

Run the application with the following command:

```
python3 app.py
```

The script will begin running & write logs to the local console.

### Docker

A docker image has been published for this container at `ghcr.io/gve-sw/gve_devnet_sdwan_ups_power_cycle`

This image can be used by creating the config & .env files as specified above - then providing them to the container image:

```
docker run --env-file <path-to-env-file> -v <path-to-config.yaml>:/app/config.yaml -d ghcr.io/gve-sw/gve_devnet_sdwan_ups_power_cycle:latest
```

Alternatively, a `docker-compose.yml` file has been included as well.

# Related Sandbox

- [Cisco SD-WAN 20.10](https://devnetsandbox.cisco.com/RM/Diagram/Index/ed2c839d-621e-4c55-b176-db2457baf4c8?diagramType=Topology)

> Note: This sandbox can only be used to test the WAN edge BFD probe monitoring. An Eaton UPS must be supplied separately in order to run the script as intended.

# Screenshots

### Demo of script

![/IMAGES/demo.gif](/IMAGES/demo.gif)

### LICENSE

Provided under Cisco Sample Code License, for details see [LICENSE](LICENSE.md)

### CODE_OF_CONDUCT

Our code of conduct is available [here](CODE_OF_CONDUCT.md)

### CONTRIBUTING

See our contributing guidelines [here](CONTRIBUTING.md)

#### DISCLAIMER

<b>Please note:</b> This script is meant for demo purposes only. All tools/ scripts in this repo are released for use "AS IS" without any warranties of any kind, including, but not limited to their installation, use, or performance. Any use of these scripts and tools is at your own risk. There is no guarantee that they have been through thorough testing in a comparable environment and we are not responsible for any damage or data loss incurred with their use.
You are responsible for reviewing and testing any scripts you run thoroughly before use in any non-testing environment.
