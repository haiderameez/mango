# Night Window Coffee design notes

On this page, a night-shift coffee receipt becomes the storefront and the one-click checkout
failure demo. The receipt carries the product, order controls and delivery state together, so
the visitor can see how an ordinary shop action becomes an application log.

The page uses the dealt **page-is-the-object** direction (seed `1082853497`): flat stone
ground, paper receipt, ink text and one blueprint-blue accent. The coffee bag is drawn in SVG
from the shop's window motif; no stock product image or customer proof is implied. The only
live action is placing an order or simulating three payment failures. The last action sends
sanitized events to Mango and leaves incident creation to Mango's configured detection rule.
