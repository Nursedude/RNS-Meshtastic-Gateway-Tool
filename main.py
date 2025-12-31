import time
import sys
import os
import RNS
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import config

# Global variables for interfaces
rns_link = None
mesh_interface = None

def program_setup():
    """
    Initialize Reticulum and Meshtastic interfaces.
    """
    global mesh_interface

    # 1. Start Reticulum
    RNS.log(f"Starting {config.APP_NAME}...", RNS.LOG_INFO)
    reticulum = RNS.Reticulum()

    # 2. Load Identity
    if not os.path.exists("storage"):
        os.makedirs("storage")

    if os.path.isfile(config.IDENTITY_FILE):
        identity = RNS.Identity.from_file(config.IDENTITY_FILE)
        RNS.log("Loaded existing Identity.", RNS.LOG_INFO)
    else:
        identity = RNS.Identity()
        identity.to_file(config.IDENTITY_FILE)
        RNS.log("Created new Identity.", RNS.LOG_INFO)

    # 3. Create RNS Destination (Server side)
    destination = RNS.Destination(
        identity,
        RNS.Destination.IN,
        RNS.Destination.SINGLE,
        config.APP_NAME,
        config.RNS_ASPECT
    )

    # Register a callback for when an RNS Link is established
    destination.set_link_established_callback(rns_link_established)

    RNS.log(f"RNS Destination active: {RNS.prettyhexrep(destination.hash)}", RNS.LOG_INFO)

    # 4. Connect to Meshtastic
    try:
        RNS.log("Connecting to Meshtastic device...", RNS.LOG_INFO)
        mesh_interface = meshtastic.serial_interface.SerialInterface(config.MESH_SERIAL_PORT)

        # Subscribe to Meshtastic message events
        pub.subscribe(on_mesh_message, "meshtastic.receive")
        RNS.log("Meshtastic connection successful.", RNS.LOG_INFO)

    except Exception as e:
        RNS.log(f"Error connecting to Meshtastic: {e}", RNS.LOG_ERROR)
        # We don't exit here so you can still test RNS parts even if Mesh fails
        RNS.log("Continuing without Meshtastic connection (Test Mode)...", RNS.LOG_WARNING)

def rns_link_established(link):
    """
    Callback when a remote RNS user connects to this gateway.
    """
    global rns_link
    rns_link = link
    RNS.log(f"RNS Link established with {RNS.prettyhexrep(link.destination_hash)}", RNS.LOG_INFO)
    link.set_packet_callback(rns_packet_received)
    link.set_link_closed_callback(rns_link_closed)

def rns_link_closed(link):
    global rns_link
    if rns_link == link:
        RNS.log("RNS Link closed.", RNS.LOG_INFO)
        rns_link = None

def rns_packet_received(data, packet):
    """
    Received data from RNS -> Forward to Meshtastic
    """
    msg_text = data.decode('utf-8')
    RNS.log(f"Received from RNS: {msg_text}", RNS.LOG_INFO)

    if mesh_interface:
        # Send text to the default Meshtastic channel
        mesh_interface.sendText(msg_text)
        RNS.log(f"Forwarded to Meshtastic: {msg_text}", RNS.LOG_INFO)

def on_mesh_message(packet, interface):
    """
    Received data from Meshtastic -> Forward to RNS
    """
    try:
        if 'decoded' in packet and 'text' in packet['decoded']:
            text_msg = packet['decoded']['text']
            sender = packet['fromId']

            log_msg = f"Mesh Msg from {sender}: {text_msg}"
            RNS.log(log_msg, RNS.LOG_INFO)

            # If we have an active RNS link, forward it
            if rns_link and rns_link.status == RNS.Link.ACTIVE:
                rns_link.send(text_msg.encode('utf-8'))
                RNS.log("Forwarded to RNS.", RNS.LOG_INFO)
            else:
                RNS.log("No active RNS link to forward message to.", RNS.LOG_DEBUG)

    except Exception as e:
        RNS.log(f"Error parsing mesh packet: {e}", RNS.LOG_ERROR)

if __name__ == "__main__":
    try:
        program_setup()
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        RNS.log("Shutting down...", RNS.LOG_INFO)
        if mesh_interface:
            mesh_interface.close()
