##
# Copyright (c) 2005-2017 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

"""
SMTP sending utility
"""

from cStringIO import StringIO

from twext.internet.adaptendpoint import connect
from twext.internet.gaiendpoint import GAIEndpoint
from twext.internet.ssl import simpleClientContextFactory
from twext.python.log import Logger
from twisted.internet import defer, reactor as _reactor
from twisted.mail.smtp import ESMTPSenderFactory, messageid
from twistedcaldav.config import config

log = Logger()


class SMTPSender(object):

    def __init__(self, username, password, useSSL, server, port):
        self.username = username
        self.password = password
        self.useSSL = useSSL
        self.server = server
        self.port = port

    def sendMessage(self, fromAddr, toAddr, msgId, message):

        log.debug("Sending: {msg}", msg=message)

        def _success(result, msgId, fromAddr, toAddr):
            log.info(
                "Sent IMIP message {id} from {fr} to {to}",
                id=msgId,
                fr=fromAddr,
                to=toAddr,
            )
            return True

        def _failure(failure, msgId, fromAddr, toAddr):
            log.error(
                "Failed to send IMIP message {id} from {fr} to {to} (Reason: {err})",
                id=msgId,
                fr=fromAddr,
                to=toAddr,
                err=failure.getErrorMessage(),
            )
            from OpenSSL.SSL import Error as TLSError
            if failure.type is TLSError:
                from calendarserver.tap.util import AlertPoster
                AlertPoster.postAlert("MailCertificateAlert", 7 * 24 * 60 * 60, [])
            return False

        deferred = defer.Deferred()

        if self.useSSL:
            contextFactory = simpleClientContextFactory(self.server)
        else:
            contextFactory = None

        factory = ESMTPSenderFactory(
            self.username, self.password,
            fromAddr, toAddr,
            # per http://trac.calendarserver.org/ticket/416 ...
            StringIO(message.replace("\r\n", "\n")), deferred,
            contextFactory=contextFactory,
            requireAuthentication=False,
            requireTransportSecurity=self.useSSL)

        connect(GAIEndpoint(_reactor, self.server, self.port),
                factory)
        deferred.addCallback(_success, msgId, fromAddr, toAddr)
        deferred.addErrback(_failure, msgId, fromAddr, toAddr)
        return deferred

    @staticmethod
    def betterMessageID():
        """
        Strip out the domain in the default Twisted Message-ID value and replace with our configured
        server host name. That will avoid leaking internal app-server host names in a multi-host setup.

        @return: our safe message-id value
        @rtype: L{str}
        """
        return "{}@{}>".format(messageid().split("@")[0], config.ServerHostName)
