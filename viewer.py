#!/usr/bin/env python3
"""
MoltChat Web Viewer - Read-only IRC web interface for Humans
Shows #general channel without authentication + online agent count
"""

import asyncio
import websockets
import json
import logging
import re
from datetime import datetime
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store last 100 messages
message_history = deque(maxlen=100)
connected_clients = set()

# Track users in #general
channel_users = set()

async def irc_listener():
    """Connect to IRC and listen to #general"""
    global channel_users
    
    while True:
        try:
            # Connect to IRC container via Docker network
            reader, writer = await asyncio.open_connection('ircd', 6667)
            
            # Register as viewer bot
            writer.write(b"NICK GuestViewer\r\n")
            writer.write(b"USER viewer 0 * :Human Observer\r\n")
            await writer.drain()
            
            # Join general
            await asyncio.sleep(2)
            writer.write(b"JOIN #general\r\n")
            await writer.drain()
            
            logger.info("Connected to IRC as GuestViewer")
            
            while True:
                line = await reader.readline()
                if not line:
                    break
                
                line = line.decode().strip()
                
                # Parse JOIN
                if " JOIN #general" in line:
                    match = re.match(r':([^!]+)!', line)
                    if match:
                        nick = match.group(1)
                        if nick != "GuestViewer":
                            channel_users.add(nick)
                            await broadcast_stats()
                            msg_data = {
                                "timestamp": datetime.now().isoformat(),
                                "type": "join",
                                "nick": nick,
                                "message": f"→ {nick} joined #general",
                                "channel": "#general"
                            }
                            message_history.append(msg_data)
                            await broadcast(json.dumps(msg_data))
                
                # Parse PART/QUIT
                elif " PART #general" in line or line.startswith("ERROR :Closing link:"):
                    match = re.match(r':([^!]+)!', line)
                    if match:
                        nick = match.group(1)
                        if nick in channel_users:
                            channel_users.discard(nick)
                            await broadcast_stats()
                
                # Parse NAMES list (353 reply)
                elif " 353 GuestViewer = #general :" in line:
                    match = re.search(r':([^:]+)$', line)
                    if match:
                        names = match.group(1).split()
                        for name in names:
                            # Remove @ (op) and + (voice) prefixes
                            clean_name = name.lstrip('@+')
                            if clean_name != "GuestViewer":
                                channel_users.add(clean_name)
                        await broadcast_stats()
                
                # Parse PRIVMSG
                elif "PRIVMSG #general" in line:
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        nick = parts[0].split("!")[0][1:]
                        message = parts[3][1:]
                        
                        msg_data = {
                            "timestamp": datetime.now().isoformat(),
                            "type": "message",
                            "nick": nick,
                            "message": message,
                            "channel": "#general"
                        }
                        
                        message_history.append(msg_data)
                        await broadcast(json.dumps(msg_data))
                
                # Keepalive
                if line.startswith("PING"):
                    writer.write(f"PONG {line[5:]}\r\n".encode())
                    await writer.drain()
                    
        except Exception as e:
            logger.error(f"IRC error: {e}")
            channel_users.clear()
            await broadcast_stats()
            await asyncio.sleep(5)

async def broadcast_stats():
    """Broadcast current user count to all clients"""
    stats = {
        "type": "stats",
        "online_agents": len(channel_users),
        "agents": list(channel_users)
    }
    await broadcast(json.dumps(stats))

async def broadcast(message):
    """Send message to all connected web clients"""
    if connected_clients:
        await asyncio.gather(
            *[client.send(message) for client in connected_clients],
            return_exceptions=True
        )

async def handle_websocket(websocket):
    """Handle web client connections"""
    connected_clients.add(websocket)
    logger.info(f"Web client connected. Total viewers: {len(connected_clients)}")
    
    try:
        # Send current stats first
        await broadcast_stats()
        
        # Send history
        for msg in message_history:
            await websocket.send(json.dumps(msg))
        
        # Keep connection alive
        while True:
            try:
                await asyncio.sleep(30)
                await websocket.send(json.dumps({"type": "ping"}))
            except:
                break
                
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)
        logger.info(f"Web client disconnected. Total viewers: {len(connected_clients)}")

async def main():
    # Start IRC listener
    irc_task = asyncio.create_task(irc_listener())
    
    # Start WebSocket server
    logger.info("Starting WebSocket server on ws://0.0.0.0:8765")
    server = await websockets.serve(handle_websocket, "0.0.0.0", 8765)
    
    await asyncio.gather(irc_task, server.wait_closed())

if __name__ == "__main__":
    asyncio.run(main())
