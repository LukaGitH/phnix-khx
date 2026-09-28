"""Async Modbus TCP client for the Phnix KHX heat pump.

Self-contained (stdlib asyncio only) so the integration has no dependency on a
particular pymodbus version.

This implements three hardening rules learned from the Waveshare RS485 bridge at
the heart of this setup - see out/README.md "Reading this bridge reliably":

1. Read ONE register per request. A multi-register request often returns a single
   register and can shift every following read by one address, silently producing
   plausible-but-wrong values.
2. Match the transaction id and discard anything else. The connection carries
   frames that are not answers to our request (this integration running beside
   HA's own modbus integration makes that worse).
3. Read 3x and take the median. The bridge occasionally answers a correct request
   with a stale frame whose transaction id happens to match.

A fresh connection per poll plus a warm-up read avoids the desynchronisation that
follows the first request on a new connection.
"""
from __future__ import annotations

import asyncio
import logging
import struct

_LOGGER = logging.getLogger(__name__)

UNIT_ID = 1
_FRAME_HEADER = struct.Struct(">HHHB")
_EXCEPTIONS = {
    1: "illegal function",
    2: "illegal data address",
    3: "illegal data value",
    4: "slave device failure",
    6: "slave device busy",
    10: "gateway path unavailable",
    11: "gateway target failed to respond",
}


class ModbusError(Exception):
    """Raised when a register cannot be read or written."""


class ModbusClient:
    """Read-only by default; writes only via write_register."""

    def __init__(self, host: str, port: int = 502, unit: int = UNIT_ID,
                 timeout: float = 5.0, delay: float = 0.3,
                 reconnect_every: int = 8) -> None:
        self.host = host
        self.port = port
        self.unit = unit
        self.timeout = timeout
        # The Waveshare/RS485 bridge needs breathing room between requests - the
        # user's modbus.yaml sets `delay: 2`. Without this, requests issued
        # back-to-back on one connection are silently dropped.
        self.delay = delay
        # rotate the TCP connection this often (see read_registers)
        self.reconnect_every = max(1, reconnect_every)
        self._txn = 0

    # -- transport ---------------------------------------------------------
    def _next_txn(self) -> int:
        self._txn = (self._txn + 1) & 0xFFFF
        return self._txn or 1

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout)
        except (OSError, asyncio.TimeoutError) as err:
            raise ModbusError(f"connect {self.host}:{self.port} failed: {err}") from err

    async def _recv_frame(self, reader: asyncio.StreamReader):
        try:
            hdr = await asyncio.wait_for(reader.readexactly(7), self.timeout)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError) as err:
            raise ModbusError(f"reading frame header: {err}") from err
        txn, _proto, length, _unit = _FRAME_HEADER.unpack(hdr)
        try:
            body = await asyncio.wait_for(reader.readexactly(length - 1), self.timeout)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError) as err:
            raise ModbusError(f"reading frame body: {err}") from err
        return txn, body

    async def _transact(self, reader, writer, pdu: bytes, expect_txn: int) -> bytes:
        """Send one PDU and return the matching response body."""
        if self.delay:
            await asyncio.sleep(self.delay)
        mbap = _FRAME_HEADER.pack(expect_txn, 0, len(pdu) + 1, self.unit)
        writer.write(mbap + pdu)
        try:
            await asyncio.wait_for(writer.drain(), self.timeout)
        except (OSError, asyncio.TimeoutError) as err:
            raise ModbusError(f"send failed: {err}") from err

        deadline = asyncio.get_event_loop().time() + self.timeout * 2
        skipped = 0
        while True:
            if asyncio.get_event_loop().time() > deadline:
                raise ModbusError(
                    f"no response for txn {expect_txn} (skipped {skipped} stale)")
            try:
                txn, body = await self._recv_frame(reader)
            except ModbusError:
                if skipped:
                    raise
                raise
            if txn != expect_txn:
                skipped += 1
                if skipped == 1:
                    _LOGGER.debug("skipping stale frame txn=%s (want %s)",
                                  txn, expect_txn)
                continue
            break

        if not body:
            raise ModbusError("empty response body")
        fc = body[0]
        if fc & 0x80:
            code = body[1] if len(body) > 1 else -1
            raise ModbusError(f"modbus exception {code}: "
                              f"{_EXCEPTIONS.get(code, 'unknown')}")
        return body

    # -- operations --------------------------------------------------------
    async def read_register(self, address: int, repeats: int = 3) -> int:
        """Read one holding register, median of `repeats` attempts."""
        reader, writer = await self._connect()
        try:
            # warm-up: the first request on a new connection is unreliable
            await self._warmup(reader, writer)
            values: list[int] = []
            for _ in range(max(1, repeats)):
                try:
                    pdu = struct.pack(">BHH", 0x03, address, 1)
                    body = await self._transact(reader, writer, pdu,
                                                self._next_txn())
                    if body[0] != 3:
                        raise ModbusError(f"unexpected function code {body[0]}")
                    count = body[1]
                    if count != 2 or len(body) < 2 + count:
                        raise ModbusError(
                            f"bad response size at {address}: bytecount={count}")
                    values.append(struct.unpack(">H", body[2:4])[0])
                except ModbusError as err:
                    _LOGGER.debug("read %s attempt failed: %s", address, err)
                    continue
            if not values:
                raise ModbusError(f"all reads failed at address {address}")
            values.sort()
            return values[len(values) // 2]
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _warmup(self, reader, writer) -> None:
        for _ in range(3):
            try:
                pdu = struct.pack(">BHH", 0x03, 1012, 1)
                await self._transact(reader, writer, pdu, self._next_txn())
                return
            except ModbusError:
                continue

    async def read_registers(self, addresses: list[int]) -> dict[int, int]:
        """Read many registers, one request per register, over rotating connections.

        Two failure modes drove this design (measured against the live bridge):
          - a fresh connection per register exhausts the bridge after ~5 requests;
          - one long-lived connection dies after ~20 and never recovers.
        So: keep a connection for `reconnect_every` registers, then rotate. If a
        read fails anyway, drop the connection and retry once on a fresh one -
        a desynchronised connection otherwise fails every subsequent read.

        Still single-register requests only: a multi-register request is what
        triggers the one-address shift.
        """
        out: dict[int, int] = {}
        reader = writer = None
        used = 0

        async def _close():
            nonlocal reader, writer
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
            reader = writer = None

        async def _open():
            nonlocal reader, writer, used
            await _close()
            r, w = await self._connect()
            reader, writer = r, w
            await self._warmup(reader, writer)
            used = 0

        try:
            for address in addresses:
                if writer is None or used >= self.reconnect_every:
                    await _open()
                try:
                    out[address] = await self._read_one(reader, writer, address)
                    used += 1
                except ModbusError as err:
                    _LOGGER.debug("read %s failed (%s); reconnecting", address, err)
                    try:
                        await _open()
                        out[address] = await self._read_one(reader, writer, address)
                        used = 1
                    except ModbusError as retry_err:
                        _LOGGER.warning("read failed for address %s: %s",
                                        address, retry_err)
                        await _close()
        finally:
            await _close()
        return out

    async def _read_one(self, reader, writer, address: int,
                        repeats: int = 1) -> int:
        values: list[int] = []
        for _ in range(max(1, repeats)):
            try:
                pdu = struct.pack(">BHH", 0x03, address, 1)
                body = await self._transact(reader, writer, pdu, self._next_txn())
                if body[0] != 3:
                    raise ModbusError(f"unexpected function code {body[0]}")
                count = body[1]
                if count != 2 or len(body) < 2 + count:
                    raise ModbusError(
                        f"bad response size at {address}: bytecount={count}")
                values.append(struct.unpack(">H", body[2:4])[0])
            except ModbusError:
                continue
        if not values:
            raise ModbusError(f"read failed at address {address}")
        values.sort()
        return values[len(values) // 2]

    async def write_register(self, address: int, value: int) -> int:
        """Write one holding register (FC 06). Returns the value written."""
        reader, writer = await self._connect()
        try:
            await self._warmup(reader, writer)
            pdu = struct.pack(">BHH", 0x06, address, value & 0xFFFF)
            await self._transact(reader, writer, pdu, self._next_txn())
            return value & 0xFFFF
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


def signed16(value: int) -> int:
    """Interpret a register as a signed 16-bit two's-complement value."""
    value = int(value) & 0xFFFF
    return value - 65536 if value >= 32768 else value
