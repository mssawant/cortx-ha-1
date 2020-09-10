import json
import logging
from queue import Queue
from typing import Any, List, Optional, Tuple

from hax.message import BroadcastHAStates
from hax.motr.delivery import DeliveryHerald
from hax.queue.confobjutil import ConfObjUtil
from hax.types import HaLinkMessagePromise, HAState, MessageId
from hax.util import create_drive_fid


class BQProcessor:
    """
    This is the place where a real processing logic should be located.
    Currently it is effectively a no-op.
    """
    def __init__(self, queue: Queue, delivery_herald: DeliveryHerald):
        self.queue = queue
        self.confobjutil = ConfObjUtil()
        self.herald = delivery_herald

    def process(self, message: Tuple[int, Any]) -> None:
        (i, msg) = message
        logging.debug('Message #%d received: %s (type: %s)', i, msg,
                      type(msg).__name__)
        self.payload_process(msg)
        logging.debug('Message #%d processed', i)

    def payload_process(self, msg: str) -> None:
        hastates = []
        try:
            msg_load = json.loads(msg)
            payload = msg_load['payload']
        except json.JSONDecodeError:
            logging.error('Cannot parse payload, invalid json')
            return
        # To add check for multiple object entries in a payload.
        # for objinfo in payload:
        hastate: Optional[HAState] = self.to_ha_state(payload)
        if hastate:
            hastates.append(hastate)
        if not hastates:
            logging.debug('No ha states to broadcast')
            return

        q: Queue = Queue(1)
        self.queue.put(BroadcastHAStates(states=hastates, reply_to=q))
        ids: List[MessageId] = q.get()
        self.herald.wait_for_any(HaLinkMessagePromise(ids))

    def to_ha_state(self, objinfo: dict) -> Optional[HAState]:
        try:
            drive_id = self.confobjutil.obj_name_to_id(objinfo['obj_type'],
                                                       objinfo['obj_name'])
        except KeyError as error:
            logging.error('Invalid json payload, no key (%s) present', error)
            return None
        return HAState(fid=create_drive_fid(int(drive_id)),
                       status=objinfo['obj_state'])