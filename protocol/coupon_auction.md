Summary

    Coupon auction using a FPSBA kind of blind auction

Description

An auction is initiated for every epoch when TWAP < 1, during that epoch people may place bids -> {how much they want to pay, max coupons they want to buy, the epoch they want coupon to expire}. Bids that exceed the max coupon to token ratio are rejected immediately (currently set to 1 DSD at risk for max 10MM coupons, can be raised/lowered later or removed entirely) and bids that exceed an expiration of 30 years are rejected immediately. Bids that are in the last 90% of outstanding are rejected to avoid masive tailing auctions. Tokens that are in the wallets at the time of bidding, but not by the time of settlement are ignored and not filled.

This is designed to dis-incentivize existing holders from buying coupons unless they are willing to risk the amount of DSD they are willing to burn, offering extremely high potential yield compared to what's available in the crypto ecosystem while naturally being capped by the varying market forces (current non redeemed best bidders across auctions; i.e. those with the most at risk) and coupon expiry for expansion and contraction, respectively.

Existing for redemption and buying will still exist as is.

Exapnsion is purely driven by the best outstanding coupon bids, there are no locks times on LP or DAO, but the states remain such that it is easy to demarkate between them and people can move freely between them as they see fit without artifitial limitations

At the end of the epoch:

    if TWAP > 1, the auction is canceled, coupons are auto-redeemed in order of placement in prior auctions that were successfully settled (i.e first place winners in each auction first, then second place, etc until redemption pool is empty, currently not possible due to gas constraints). Rate of expansion is determined by prior auction internals (sum of the current best bidders in previous auctions that still have non expired coupons in them, this will allow for market driven dynamics to determine the rate of token growth), not by hard-coding in the protocol.

    if TWAP < 1, the auction is settled and coupons assigned in order and tracked on chain within an auction based on min euclidean distance of yield and expiry (i.e. the person that submitted the smallest yield, smallest expiry gets filled first and the most amount of esd they are willing to burn) until all are filled, the next auction is created.

Tests have been implemented for coupon bidding and auction settlement (auto-redemption tests are in progress, existing supply tests need to be modified). Thanks to everyone for helping me flesh this out in the discord conversations.