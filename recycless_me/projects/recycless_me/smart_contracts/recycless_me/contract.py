import algopy
from algopy import ARC4Contract, arc4, GlobalState, LocalState, Txn, UInt64

class SimpleRecycle(ARC4Contract):
    """Simple recycling tracker"""
    
    def __init__(self) -> None:
        self.total_recycled = GlobalState(UInt64(0))
        self.user_recycled = LocalState(UInt64)
    
    @arc4.abimethod(create="require")
    def create(self) -> None:
        """Initialize the app"""
        self.total_recycled.value = UInt64(0)
    
    @arc4.baremethod(allow_actions=["OptIn"])
    def opt_in(self) -> None:
        """Allow users to opt-in to the app"""
        pass
    
    @arc4.abimethod
    def recycle_item(self) -> arc4.UInt64:
        """User recycles one item"""
        # Update total count
        self.total_recycled.value += UInt64(1)
        
        # Update user count
        user_current = self.user_recycled.get(Txn.sender, default=UInt64(0))
        new_count = user_current + UInt64(1)
        self.user_recycled[Txn.sender] = new_count
        
        return arc4.UInt64(new_count)
    
    @arc4.abimethod(readonly=True)
    def get_total(self) -> arc4.UInt64:
        """Get total items recycled"""
        return arc4.UInt64(self.total_recycled.value)
    
    @arc4.abimethod(readonly=True)
    def get_my_count(self) -> arc4.UInt64:
        """Get current user's recycled count"""
        user_count = self.user_recycled.get(Txn.sender, default=UInt64(0))
        return arc4.UInt64(user_count)
