# -*- coding: utf-8 -*-
# Copyright: (C) 2018 Lovac42
# Support: https://github.com/lovac42/HoardersDelight
# License: GNU GPL, version 3 or later; http://www.gnu.org/copyleft/gpl.html
# Version: 0.0.1


# == User Config =========================================

HOARDERS_DECK_NAME = "~[ Hoarders Recycle Bin ]"

# == End Config ==========================================
##########################################################

# Based on SlackersDelight, used as a template to develope this.

import aqt, time
import anki.sched
from aqt import mw
from aqt.qt import *
from aqt.reviewer import Reviewer
from anki.hooks import addHook, wrap
from anki.utils import intTime, ids2str
from aqt.utils import showWarning, showInfo, tooltip, getText
from anki import version
ANKI21 = version.startswith("2.1.")


TRASHBIN_DECK_DESC = """
<p><i>This is a deck full of deleted
 cards for hoarders.</i></p><p>
<b>Warning:</b> On mobile, or without this addon,<br>
clicking empty will undelete everything.<br>
Learning cards also loose their status."""



PURGE=False #Used as a flag on 2.1 to access the real _old method.


class HoardersDelight:
    def __init__(self):
        self.timeId=intTime()%100000

    def recycle(self, ids):
        "main operations"
        global PURGE
        did = self.getDynId()
        if did:
            mw.col.log(did,ids)
            if self.isAllTrash(did,ids):
                PURGE=True
                mw.col.remCards(ids)
                return
            mw.col.sched.remFromDyn(ids)
            self.swap(did, ids)

    def getDynId(self):
        "Built or select Dyn deck"
        dyn=mw.col.decks.byName(_(HOARDERS_DECK_NAME))
        if not dyn: #Create filtered deck
            did =  mw.col.decks.id(_(HOARDERS_DECK_NAME), 
                        type=anki.decks.defaultDynamicDeck)
            dyn = mw.col.decks.get(did)
            dyn['resched']=False
        elif not dyn['dyn']: #Regular deck w/ same name
            showInfo("Please rename the existing %s deck first."%HOARDERS_DECK_NAME)
            return False
        return dyn['id']

    def swap(self, dynId, ids):
        "Swap card info"
        d = []
        mod = intTime()
        for id in ids:
            card=mw.col.getCard(id)
            odid=card.did
            if card.queue in (1,3) and mw.col.sched.name != "std2":
                #fix bad cards during db check
                odue=mw.col.sched.today
                due=card.due
            else: #new/rev cards
                odue=card.due
                due=-self.timeId
                self.timeId+=1

            d.append(dict(id=id, did=dynId, odid=odid, 
            due=due, odue=odue, mod=mod, usn=mw.col.usn()))

        mw.col.db.executemany("""
update cards set due=:due,odue=:odue,
did=:did,odid=:odid,
usn=:usn,mod=:mod where id=:id""", d)


    def isAllTrash(self, dynId, ids):
        for id in ids:
            card=mw.col.getCard(id)
            if card.did!=dynId:
                return False
        return True

    def emptyTrash(self, dynId):
        global PURGE
        t,ok=getText("""Empty Recycle Bin? Type: I Shall Not Hoard""")
        if ok and t.lower()=="i shall not hoard":
            PURGE=True
            cids = mw.col.db.list(
                "select id from cards where did=?", dynId)
            mw.col.remCards(cids)
            return True
        return False


hd=HoardersDelight()


##########################################################
# ALL MONKEY PATCH CR..Stuff BELOW #######################


def sd_answerCard(self, card, ease, _old):
    dyn = mw.col.decks.get(card.did)
    if dyn['name'] != HOARDERS_DECK_NAME:
        return _old(self, card, ease)


#Friendly Warning Message
def desc(self, deck, _old):
    if deck['name'] != HOARDERS_DECK_NAME:
        return _old(self, deck)
    return TRASHBIN_DECK_DESC


def sd_remCards(self, ids, notes=True, _old=None):
    "Bulk delete cards by ID."
    global PURGE
    if not ids: return
    if PURGE:
        _old(self, ids, notes)
        PURGE=False
        return
    hd.recycle(ids)


def sd_emptyDyn(self, did, lim=None, _old=None):
    dyn = mw.col.decks.get(did)
    if dyn['name'] != HOARDERS_DECK_NAME:
        return _old(self, did, lim)

    if not lim:
        return hd.emptyTrash(did)

    self.col.log(self.col.db.list("select id from cards where %s" % lim))
    self.col.db.execute("""
update cards set did = odid,
due = (case when queue in (1,3) then due else odue end),
odue = 0, odid = 0, usn = ? where %s""" %
lim, self.col.usn())



def rem(self, did, cardsToo=False, childrenToo=True, _old=None):
    dyn = mw.col.decks.get(did)
    if dyn['name'] != HOARDERS_DECK_NAME:
        return _old(self, did, cardsToo, childrenToo)

    if mw.col.sched.emptyDyn(did):
        # delete the deck and add a grave
        del self.decks[str(did)]
        # ensure we have an active deck
        if did in self.active():
            self.select(int(self.decks.keys()[0]))
        self.save()


# In case user changes decks in Browser or other altercations.
# Since the Deck ID is not given, we are checking each card one by one.
# This is a taxing process, so we are limiting it to 10 cards max.
# If more than 10, we are using the first card only.
# Trashbin deck and normal decks should not be mixed.
def sd_remFromDyn(self, cids, _old):
    if len(cids)>10:
        did=mw.col.getCard(cids[0]).did
        self.emptyDyn(did, "id in %s and odid" % ids2str(cids))
    else:
        for id in cids:
            did=mw.col.getCard(id).did
            self.emptyDyn(did, "id = %d and odid" % id)


#Prevent user from rebuilding this special deck
def sd_rebuildDyn(self, did=None, _old=None):
    did = did or self.col.decks.selected()
    dyn = mw.col.decks.get(did)
    if dyn['name'] == HOARDERS_DECK_NAME:
        showWarning("Can't modify this deck.") 
        return None
    return _old(self, did)


#Prevent user from changing deck options
def sd_onDeckConf(self, deck=None, _old=None):
    if not deck:
        deck = self.col.decks.current()
    if deck['name'] == HOARDERS_DECK_NAME:
        showWarning("Can't modify this deck.") 
        return
    return _old(self, deck)


aqt.main.AnkiQt.onDeckConf = wrap(aqt.main.AnkiQt.onDeckConf, sd_onDeckConf, 'around')
aqt.overview.Overview._desc = wrap(aqt.overview.Overview._desc, desc, 'around')
anki.sched.Scheduler.emptyDyn = wrap(anki.sched.Scheduler.emptyDyn, sd_emptyDyn, 'around')
anki.sched.Scheduler.remFromDyn = wrap(anki.sched.Scheduler.remFromDyn, sd_remFromDyn, 'around')
anki.sched.Scheduler.rebuildDyn = wrap(anki.sched.Scheduler.rebuildDyn, sd_rebuildDyn, 'around')
anki.sched.Scheduler.answerCard = wrap(anki.sched.Scheduler.answerCard, sd_answerCard, 'around')
anki.collection._Collection.remCards = wrap(anki.collection._Collection.remCards, sd_remCards, 'around')
anki.decks.DeckManager.rem=wrap(anki.decks.DeckManager.rem, rem, 'around')

if ANKI21:
    import anki.schedv2
    anki.schedv2.Scheduler.rebuildDyn = wrap(anki.schedv2.Scheduler.rebuildDyn, sd_rebuildDyn, 'around')
    anki.schedv2.Scheduler.answerCard = wrap(anki.schedv2.Scheduler.answerCard, sd_answerCard, 'around')
