@RFC0211 @AIP20
Feature: RFC 0211 Aries Agent Mediator Coordination
  In order to coordinate mediation with another agent,
  As a recipient,
  I want to use the Coordinate Mediation (RFC0211) protocol to accomplish this.

  @T001-RFC0211 @critical @AcceptanceTest
  Scenario Outline: Request mediation with the mediator accepting the mediation request
    Given we have "2" agents
      | name | role      |
      | Acme | recipient |
      | Bob  | mediator  |
    And "Bob" and "Acme" create a new connection
    When "Acme" requests mediation from "Bob"
    And "Bob" grants the mediation request from "Acme"
    Then "Acme" has "Bob" set up as a mediator

    @DIDExchangeConnection
    Examples: DIDExchange connection
      | connection  |
      | didexchange |

    @RFC0160
    Examples: 0160 connection
      | connection |
      | 0160       |

  @T002-RFC0211 @critical @AcceptanceTest
  Scenario Outline: Request mediation with the mediator accepting the mediation request and creating a connection using the mediator
    Given we have "2" agents
      | name  | role      |
      | Acme  | recipient |
      | Bob   | mediator  |
      | Faber | sender    |
    And "Bob" and "Acme" create a new connection
    When "Acme" requests mediation from "Bob"
    And "Bob" grants the mediation request from "Acme"
    Then "Acme" has "Bob" set up as a mediator
    When "Acme" uses "Bob" as a mediator
    And "Acme" and "Faber" create a new connection

    @DIDExchangeConnection
    Examples: DIDExchange connection
      | connection  |
      | didexchange |

    @RFC0160
    Examples: 0160 connection
      | connection |
      | 0160       |

  # For agents without an endpoint to request mediation, the mediation needs to be automatically granted using return routing
  # Otherwise the mediator agent has no endpoint to send the mediation grant message to. However this means we can't test for
  # mediation deny, as the grant is automatically send. For now testing agents without inbound endpoint is more important
  @T003-RFC0211 @critical @AcceptanceTest @wip
  Scenario Outline: Request mediation with the mediator denying the mediation request
    Given we have "2" agents
      | name | role      |
      | Acme | recipient |
      | Bob  | mediator  |
    And "Bob" and "Acme" create a new connection
    When "Acme" requests mediation from "Bob"
    And "Bob" denies the mediation request from "Acme"
    Then "Bob" has denied the mediation request from "Acme"

    @DIDExchangeConnection
    Examples: DIDExchange connection
      | connection  |
      | didexchange |

    @RFC0160
    Examples: 0160 connection
      | connection |
      | 0160       |


  @T004-RFC0211 @UsesCustomParameters @RFC0025 @Transport_Http @Transport_Ws @normal @AcceptanceTest @allure.issue:https://github.com/openwallet-foundation/credo-ts/issues/2042 @allure.issue:https://github.com/openwallet-foundation/credo-ts/issues/2041
  Scenario Outline: Two agents creating a connection using a mediator without having inbound transports
    Given we have "2" agents
      | name  | role      |
      | Acme  | recipient |
      | Bob   | mediator  |
      | Faber | sender    |
    And "Acme" is running with parameters "{"inbound_transports": <acme-inbound-transports>, "outbound_transports": <acme-outbound-transports> }"
    And "Bob" is running with parameters "{"inbound_transports": <bob-inbound-transports>, "outbound_transports": <bob-outbound-transports> }"
    And "Faber" is running with parameters "{"inbound_transports": <faber-inbound-transports>, "outbound_transports": <faber-outbound-transports> }"

    # Create connection, request mediation
    When "Bob" and "Acme" create a new connection
    And "Acme" requests mediation from "Bob"
    And "Bob" grants the mediation request from "Acme"
    Then "Acme" has "Bob" set up as a mediator

    When "Bob" and "Faber" create a new connection
    And "Faber" requests mediation from "Bob"
    And "Bob" grants the mediation request from "Faber"
    Then "Faber" has "Bob" set up as a mediator

    # Create connection through the mediator
    When "Acme" uses "Bob" as a mediator
    And "Faber" uses "Bob" as a mediator
    And "Faber" and "Acme" create a new connection

    @DIDExchangeConnection
    Examples: Acme and Faber creating a DIDExchange connection using Bob as a mediator without having inbound transports
      | acme-inbound-transports | acme-outbound-transports | bob-inbound-transports | bob-outbound-transports | faber-inbound-transports | faber-outbound-transports |
      | []                      | ["ws", "http"]           | ["ws", "http"]         | ["ws", "http"]          | []                       | ["ws", "http"]            |

    @RFC0160
    Examples: Acme and Faber creating a 0160 connection using Bob as a mediator without having inbound transports
      | acme-inbound-transports | acme-outbound-transports | bob-inbound-transports | bob-outbound-transports | faber-inbound-transports | faber-outbound-transports |
      | []                      | ["ws", "http"]           | ["ws", "http"]         | ["ws", "http"]          | []                       | ["ws", "http"]            |


  # Not all agents support being started without inbound transports. So this tests uses mediation, but with inbound transports
  @T005-RFC0211 @UsesCustomParameters @RFC0025 @Transport_Http @Transport_Ws @critical @AcceptanceTest
  Scenario Outline: Two agents creating a connection using a mediator with overlapping transports
    Given we have "2" agents
      | name  | role      |
      | Acme  | recipient |
      | Bob   | mediator  |
      | Faber | sender    |
    And "Acme" is running with parameters "{"inbound_transports": <acme-inbound-transports>, "outbound_transports": <acme-outbound-transports> }"
    And "Bob" is running with parameters "{"inbound_transports": <bob-inbound-transports>, "outbound_transports": <bob-outbound-transports> }"
    And "Faber" is running with parameters "{"inbound_transports": <faber-inbound-transports>, "outbound_transports": <faber-outbound-transports> }"

    # Create connection, request mediation
    When "Bob" and "Acme" create a new connection
    And "Acme" requests mediation from "Bob"
    And "Bob" grants the mediation request from "Acme"
    Then "Acme" has "Bob" set up as a mediator

    When "Bob" and "Faber" create a new connection
    And "Faber" requests mediation from "Bob"
    And "Bob" grants the mediation request from "Faber"
    Then "Faber" has "Bob" set up as a mediator

    # Create connection through the mediator
    When "Acme" uses "Bob" as a mediator
    And "Faber" uses "Bob" as a mediator
    And "Faber" and "Acme" create a new connection

    @DIDExchangeConnection
    Examples: Acme and Faber creating a DIDExchange connection using Bob a mediator with overlapping transports
      | acme-inbound-transports | acme-outbound-transports | bob-inbound-transports | bob-outbound-transports | faber-inbound-transports | faber-outbound-transports |
      | ["http", "ws"]          | ["http", "ws"]           | ["http", "ws"]         | ["http", "ws"]          | ["http", "ws"]           | ["http", "ws"]            |

    @RFC0160
    Examples: Acme and Faber creating a 0160 connection using Bob a mediator with overlapping transports
      | acme-inbound-transports | acme-outbound-transports | bob-inbound-transports | bob-outbound-transports | faber-inbound-transports | faber-outbound-transports |
      | ["http", "ws"]          | ["http", "ws"]           | ["http", "ws"]         | ["http", "ws"]          | ["http", "ws"]           | ["http", "ws"]            |
