# No reversal within a route

A route is a strict pass-through: a train enters each block at one end and
exits at the other, so terminal blocks can never be intermediate. Physically a
DCC loco can reverse anywhere, so allowing exit-via-entry-end was a real
option; we rejected it because every train necessarily stops in a terminal
block anyway — typically to switch locomotive or driver — so departing again
is naturally a new request. Reversal happens between requests, at rest, which
keeps the routing graph a simple directed traversal and keeps mid-route state
out of the deadlock analysis.
