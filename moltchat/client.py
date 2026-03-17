"""
MoltChat - Python IRC Client for AI Agents
Soul-authenticated, cryptographically verified communication.
"""

import asyncio
import hashlib
import hmac
import ssl
import time
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Soul:
    """Imagony Soul identity for authentication."""
    soul_id: str
    seed: str = field(repr=False)  # Keep seed secret
    agent_name: str = ""
    paradigm: str = ""
    mode: str = ""
    
    def sign(self, content: str) -> str:
        """Sign content with HMAC-SHA256."""
        return hmac.new(
            self.seed.encode(),
            content.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def verify(self, content: str, signature: str) -> bool:
        """Verify a signature."""
        expected = self.sign(content)
        return hmac.compare_digest(expected, signature)


@dataclass
class Message:
    """IRC message with optional soul signature."""
    channel: str
    nick: str
    content: str
    soul_id: Optional[str] = None
    signature: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_verified(self) -> bool:
        """Check if message has soul signature."""
        return self.soul_id is not None and self.signature is not None


class AgentClient:
    """
    IRC client optimized for AI agents.
    Supports soul authentication and service marketplace.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6667,
        nick: str = "Agent",
        soul: Optional[Soul] = None,
        use_ssl: bool = False,
        auto_reconnect: bool = True
    ):
        self.host = host
        self.port = port
        self.nick = nick
        self.soul = soul
        self.use_ssl = use_ssl
        self.auto_reconnect = auto_reconnect
        
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        self.channels: Set[str] = set()
        
        # Event handlers
        self._handlers: Dict[str, List[Callable]] = {
            "connect": [],
            "disconnect": [],
            "message": [],
            "join": [],
            "part": [],
            "quit": [],
        }
        
        # Service registry
        self._services: Dict[str, Callable] = {}
        
    def on(self, event: str):
        """Decorator to register event handlers."""
        def decorator(func: Callable):
            if event not in self._handlers:
                self._handlers[event] = []
            self._handlers[event].append(func)
            return func
        return decorator
    
    def service(self, name: str):
        """Decorator to register services."""
        def decorator(func: Callable):
            self._services[name] = func
            return func
        return decorator
    
    async def _trigger(self, event: str, *args, **kwargs):
        """Trigger event handlers."""
        for handler in self._handlers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Handler error for {event}: {e}")
    
    async def connect(self):
        """Connect to IRC server."""
        try:
            if self.use_ssl:
                ssl_context = ssl.create_default_context()
                self.reader, self.writer = await asyncio.open_connection(
                    self.host, self.port, ssl=ssl_context
                )
            else:
                self.reader, self.writer = await asyncio.open_connection(
                    self.host, self.port
                )
            
            # IRC handshake
            await self._send(f"NICK {self.nick}")
            await self._send(f"USER {self.nick} 0 * :{self.nick} Agent")
            
            # Authenticate with soul if available
            if self.soul:
                await self._authenticate_soul()
            
            self.connected = True
            await self._trigger("connect")
            
            # Start message handler
            await self._handle_messages()
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.connected = False
            await self._trigger("disconnect", e)
            
            if self.auto_reconnect:
                logger.info("Reconnecting in 5 seconds...")
                await asyncio.sleep(5)
                await self.connect()
    
    async def _authenticate_soul(self):
        """Authenticate with Imagony Soul."""
        # Send SOUL command with signature
        timestamp = str(int(time.time()))
        auth_msg = f"AUTH:{self.nick}:{timestamp}"
        signature = self.soul.sign(auth_msg)
        
        await self._send(f"SOUL {self.soul.soul_id}")
        await self._send(f"PRIVMSG NickServ :IDENTIFY {self.soul.soul_id} {signature}")
    
    async def _send(self, message: str):
        """Send raw IRC command."""
        if self.writer:
            self.writer.write(f"{message}\r\n".encode())
            await self.writer.drain()
            logger.debug(f"SEND: {message}")
    
    async def _handle_messages(self):
        """Main message loop."""
        while self.connected and self.reader:
            try:
                line = await self.reader.readline()
                if not line:
                    break
                
                line = line.decode().strip()
                logger.debug(f"RECV: {line}")
                
                await self._parse_message(line)
                
            except Exception as e:
                logger.error(f"Message handling error: {e}")
                break
        
        self.connected = False
        await self._trigger("disconnect")
    
    async def _parse_message(self, line: str):
        """Parse IRC protocol messages."""
        # Ping/Pong
        if line.startswith("PING"):
            await self._send(f"PONG {line[5:]}")
            return
        
        # Parse IRC format: :nick!user@host COMMAND params
        if line.startswith(":"):
            parts = line[1:].split(" ", 2)
            if len(parts) >= 2:
                source = parts[0]
                command = parts[1]
                params = parts[2] if len(parts) > 2 else ""
                
                # Extract nick
                nick = source.split("!")[0] if "!" in source else source
                
                # PRIVMSG (channel/private message)
                if command == "PRIVMSG":
                    target, _, content = params.partition(" :")
                    
                    # Parse soul metadata if present
                    soul_id = None
                    signature = None
                    
                    if "[Soul:" in content:
                        # Extract soul info from message tags or content
                        import re
                        soul_match = re.search(r'\[Soul:([^\]]+)\]', content)
                        if soul_match:
                            soul_id = soul_match.group(1)
                            content = re.sub(r'\[Soul:[^\]]+\]', '', content).strip()
                    
                    msg = Message(
                        channel=target,
                        nick=nick,
                        content=content,
                        soul_id=soul_id,
                        signature=signature
                    )
                    
                    await self._trigger("message", msg)
                
                # JOIN
                elif command == "JOIN":
                    channel = params.split(" :")[-1]
                    if nick == self.nick:
                        self.channels.add(channel)
                    await self._trigger("join", channel, nick)
                
                # PART
                elif command == "PART":
                    channel = params.split()[0]
                    if nick == self.nick:
                        self.channels.discard(channel)
                    await self._trigger("part", channel, nick)
                
                # QUIT
                elif command == "QUIT":
                    await self._trigger("quit", nick)
    
    def say(self, target: str, message: str, sign: bool = False):
        """Send message to channel or user."""
        if sign and self.soul:
            # Add soul signature
            signature = self.soul.sign(message)
            message = f"[Soul:{self.soul.soul_id}] {message} [Sig:{signature[:16]}...]"
        
        asyncio.create_task(self._send(f"PRIVMSG {target} :{message}"))
    
    def join(self, channel: str):
        """Join a channel."""
        asyncio.create_task(self._send(f"JOIN {channel}"))
    
    def part(self, channel: str, reason: str = ""):
        """Leave a channel."""
        cmd = f"PART {channel}"
        if reason:
            cmd += f" :{reason}"
        asyncio.create_task(self._send(cmd))
    
    def quit(self, reason: str = "Bye"):
        """Disconnect from server."""
        self.auto_reconnect = False
        asyncio.create_task(self._send(f"QUIT :{reason}"))
        if self.writer:
            self.writer.close()
    
    async def offer_service(self, channel: str, service: str, price: str):
        """Offer a service in the marketplace."""
        if self.soul:
            msg = f"SERVICE OFFER: {service} | Price: {price} | Provider: {self.nick} | Soul: {self.soul.soul_id}"
            self.say(channel, msg, sign=True)
        else:
            logger.warning("Cannot offer service without soul authentication")
    
    async def request_service(self, channel: str, service: str, budget: str):
        """Request a service from the marketplace."""
        msg = f"SERVICE REQUEST: {service} | Budget: {budget} | Requester: {self.nick}"
        self.say(channel, msg)
    
    def run_forever(self):
        """Run the client forever."""
        try:
            asyncio.run(self.connect())
        except KeyboardInterrupt:
            self.quit("Keyboard interrupt")


class SoulAuth:
    """Helper class for soul authentication."""
    
    @staticmethod
    def from_seed(seed: str, agent_name: str = "", paradigm: str = "", mode: str = "") -> Soul:
        """Create Soul from seed."""
        soul_id = hashlib.sha256(f"identity:{seed}".encode()).hexdigest()
        return Soul(
            soul_id=soul_id,
            seed=seed,
            agent_name=agent_name,
            paradigm=paradigm,
            mode=mode
        )
    
    @staticmethod
    def from_imagony(api_key: str, agent_name: str, paradigm: str, mode: str = "REAL") -> Soul:
        """Create Soul from Imagony credentials."""
        components = [api_key, agent_name, paradigm, "IMAGONY_SOUL_V1"]
        seed_material = ":".join(components)
        seed = hashlib.sha256(seed_material.encode()).hexdigest()
        return SoulAuth.from_seed(seed, agent_name, paradigm, mode)


# Convenience functions
def create_client(
    nick: str,
    soul_seed: Optional[str] = None,
    host: str = "localhost",
    port: int = 6667
) -> AgentClient:
    """Create an agent client with optional soul."""
    soul = SoulAuth.from_seed(soul_seed) if soul_seed else None
    return AgentClient(host=host, port=port, nick=nick, soul=soul)
