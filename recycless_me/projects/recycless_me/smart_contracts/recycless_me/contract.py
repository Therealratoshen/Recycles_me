import algopy
from algopy import ARC4Contract, UInt64, Account, Txn, Global, LocalState, GlobalState, arc4, itxn

class RecycleTracker(ARC4Contract):
    """
    Recycle bottle tracker + ASA rewards.

    - Global: bottle_count (total)
    - Local:  user_count[addr]
    - Global: reward_asset_id (ASA to pay)
    - Global: reward_per_bottle (tokens per bottle)
    - Local:  is_station[addr] (1/0) for authorized stations
    """

    def __init__(self) -> None:
        # Admin / config
        self.admin = GlobalState(Account, key="admin")
        self.reward_asset_id = GlobalState(UInt64, key="reward_asset_id")   # 0 = unset
        self.reward_per_bottle = GlobalState(UInt64, key="reward_per_bottle")  # default 1

        # Counters
        self.bottle_count = GlobalState(UInt64, key="bottle_count")
        self.user_count = LocalState(UInt64, key="user_count")

        # Roles
        self.is_station = LocalState(UInt64, key="is_station")  # 1 = station

    # --- lifecycle / init ---
    @arc4.abimethod(allow_actions=["NoOp"], create=True)
    def create(self) -> None:
        """Call on create: sets creator as admin and default reward rate = 1."""
        self.admin = Txn.sender
        self.reward_asset_id = UInt64(0)
        self.reward_per_bottle = UInt64(1)
        self.bottle_count = UInt64(0)

    # --- admin: configure reward token and rate ---
    @arc4.abimethod
    def set_reward_config(self, asset_id: arc4.UInt64, per_bottle: arc4.UInt64) -> None:
        assert Txn.sender == self.admin, "only admin"
        aid = asset_id.decode()
        rate = per_bottle.decode()
        assert rate > UInt64(0), "rate must be > 0"
        self.reward_asset_id = aid
        self.reward_per_bottle = rate

    @arc4.abimethod
    def set_station(self, account: Account, is_station: arc4.Bool) -> None:
        assert Txn.sender == self.admin, "only admin"
        self.is_station[account] = UInt64(1) if bool(is_station) else UInt64(0)

    # --- app account opts into ASA so it can hold/send rewards ---
    @arc4.abimethod
    def app_opt_in_reward_asset(self) -> None:
        """
        App account opts-in to reward ASA via inner txn (0-amount axfer to self).
        Requires the app account to be funded with enough Algos for min-balance + fee.
        """
        aid = self.reward_asset_id.value
        assert aid != UInt64(0), "reward asset not set"
        itxn.AssetTransfer(
            xfer_asset=aid,
            asset_amount=UInt64(0),
            asset_receiver=Global.current_application_address,  # app opts in
            asset_sender=None,  # not a clawback; normal opt-in
            fee=UInt64(0)  # let the AVM cover from app balance; flat fee mode
        ).submit()

    # --- core actions ---
    @arc4.abimethod
    def add_bottle(self) -> UInt64:
        """User increments own count by 1 and receives reward."""
        self._increment_and_reward(Txn.sender, UInt64(1))
        return self.bottle_count.value

    @arc4.abimethod
    def add_bottles(self, amount: arc4.UInt64) -> UInt64:
        """Station-only batch add for the caller (e.g., weighed drop-off)."""
        assert self.is_station.get(Txn.sender, UInt64(0)) == UInt64(1), "station only"
        inc = amount.decode()
        assert inc > UInt64(0), "amount must be > 0"
        self._increment_and_reward(Txn.sender, inc)
        return self.bottle_count.value

    @arc4.abimethod
    def add_bottles_for(self, user: Account, amount: arc4.UInt64) -> UInt64:
        """Station-only batch add for a specified user (QR scanned at depot)."""
        assert self.is_station.get(Txn.sender, UInt64(0)) == UInt64(1), "station only"
        inc = amount.decode()
        assert inc > UInt64(0), "amount must be > 0"
        self._increment_and_reward(user, inc)
        return self.bottle_count.value

    # --- views ---
    @arc4.abimethod(readonly=True)
    def get_bottle_count(self) -> UInt64:
        return self.bottle_count.value

    @arc4.abimethod(readonly=True)
    def get_user_count(self, account: Account) -> UInt64:
        return self.user_count.get(account, UInt64(0))

    # --- internal helpers ---
    def _increment_and_reward(self, receiver: Account, inc: UInt64) -> None:
        # update counters
        self.bottle_count += inc
        self.user_count[receiver] = self.user_count.get(receiver, UInt64(0)) + inc

        # reward if configured
        aid = self.reward_asset_id.value
        if aid != UInt64(0):
            # amount = inc * rate
            amt = inc * self.reward_per_bottle.value

            # inner axfer from the app's ASA balance to the receiver
            itxn.AssetTransfer(
                xfer_asset=aid,
                asset_amount=amt,
                asset_receiver=receiver,
                fee=UInt64(0)
            ).submit()
