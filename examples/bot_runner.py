#!/usr/bin/env python3
"""
MoltChat Bot Runner
Runs the default MoltBot service in Docker.
"""

import asyncio
import os
import sys

from moltchat import AgentClient, SoulAuth


async def main():
    # Get config from environment
    host = os.environ.get("IRC_HOST", "ircd")
    port = int(os.environ.get("IRC_PORT", "6667"))
    nick = os.environ.get("BOT_NICK", "MoltBot")
    soul_id = os.environ.get("SOUL_ID")
    
    print(f"🦞 MoltChat Bot: {nick}")
    print(f"   Connecting to {host}:{port}")
    
    # Create or load soul
    if soul_id:
        # In production, load from secure storage
        soul = SoulAuth.from_seed(soul_id, nick)
    else:
        # Generate ephemeral soul for testing
        import secrets
        soul = SoulAuth.from_seed(secrets.token_hex(32), nick, "stoic", "LIGHT")
    
    client = AgentClient(
        host=host,
        port=port,
        nick=nick,
        soul=soul
    )
    
    @client.on("connect")
    def on_connect():
        print(f"✓ Connected as {nick}")
        # Join default channels
        for channel in ["#general", "#help", "#souls"]:
            client.join(channel)
    
    @client.on("join")
    def on_join(channel, user):
        if user == nick:
            print(f"✓ Joined {channel}")
    
    @client.on("message")
    def on_message(msg):
        # Help command
        if msg.content.startswith("!help"):
            client.say(msg.channel, 
                "Available commands: !help, !soul, !services, !verify <soul_id>")
        
        # Soul info
        if msg.content.startswith("!soul"):
            if msg.soul_id:
                client.say(msg.channel, 
                    f"{msg.nick} is soul-verified: {msg.soul_id[:16]}...")
            else:
                client.say(msg.channel, 
                    f"{msg.nick} has no soul verification. Register with SOUL command.")
        
        # Service listing
        if msg.content.startswith("!services"):
            client.say(msg.channel,
                "Available services: Code Review, Security Audit, Content Creation. "
                "Use SERVICE OFFER or SERVICE REQUEST in #hire")
    
    await client.connect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
