# Dispatch

The dispatcher accepts route requests from the scheduler and tries to satisfy
them in the shortest time possible.

**Time model:** each transition through a connection (vertex) takes one unit of
time, e.g. one minute. Travel time within blocks is ignored.

Dispatching is a complex task in general. It includes:

1. **Find** a route satisfying the request, or reject the request if no such
   route exists.
2. **Lock** the route and assign it to a driver.
3. **Unlock** the route once the assigned train has passed, making it available
   for new requests.
4. **Lock lazily** to optimize total throughput: reserve only the parts of a
   route needed for the train to advance — usually the block the train is in
   plus the next block in the route.

   Lazy locking can deadlock. Two trains entering a section of two facing blocks
   with no other connections between them each wait for the other to depart.
   Avoiding this, e.g. with a reservation scheme, is what makes dispatching
   challenging.
5. **Optimize speed** by exploiting complex connectors that admit several trains
   at once. The connector below accepts two trains simultaneously on its two
   straight sections, but only one train at a time on either crossing route.

   ![Crossing connector](image.png)
