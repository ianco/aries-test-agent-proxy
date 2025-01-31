@RFC0037
Feature: RFC 0037 Aries agent present proof

   @T001-RFC0037 @AIP10 @critical @AcceptanceTest @Indy
   Scenario Outline: Present Proof where the prover does not propose a presentation of the proof and is acknowledged
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" have an existing connection
      And "Bob" has an issued credential from <issuer>
      When "Faber" sends a request for proof presentation to "Bob"
      And "Bob" makes the presentation of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer |
         | Acme   |
         | Faber  |

   @T001.1-RFC0037 @AIP20 @critical @AcceptanceTest @Indy @DIDExchangeConnection
   Scenario Outline: Present Proof where the prover does not propose a presentation of the proof and is acknowledged with a DID Exchange Connection
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" have an existing connection
      And "Bob" has an issued credential from <issuer>
      When "Faber" sends a request for proof presentation to "Bob"
      And "Bob" makes the presentation of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer |
         | Acme   |
         | Faber  |

   @T001.2-RFC0037 @AIP10 @critical @AcceptanceTest @Schema_DriversLicense @Indy
   Scenario Outline: Present Proof of specific types and proof is acknowledged with a Drivers License credential type
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" have an existing connection
      And "Bob" has an issued credential from <issuer> with <credential_data>
      When "Faber" sends a <request_for_proof> presentation to "Bob"
      And "Bob" makes the <presentation> of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer | credential_data   | request_for_proof            | presentation                |
         | Acme   | Data_DL_MaxValues | proof_request_DL_address     | presentation_DL_address     |
         | Faber  | Data_DL_MinValues | proof_request_DL_age_over_19 | presentation_DL_age_over_19 |


   @T001.3-RFC0037 @AIP10 @critical @AcceptanceTest @Schema_Biological_Indicators @Indy
   Scenario Outline: Present Proof of specific types and proof is acknowledged with a Biological Indicators credential type
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" have an existing connection
      And "Bob" has an issued credential from <issuer> with <credential_data>
      When "Faber" sends a <request for proof> presentation to "Bob"
      And "Bob" makes the <presentation> of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer | credential_data          | request for proof                    | presentation                        |
         | Acme   | Data_BI_NormalizedValues | proof_request_biological_indicator_a | presentation_biological_indicator_a |

   @T001.4-RFC0037 @AIP10 @critical @AcceptanceTest @Schema_Biological_Indicators @Schema_Health_Consent @Indy
   Scenario Outline: Present Proof of specific types and proof is acknowledged with multiple credential types
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" have an existing connection
      And "Bob" has an issued credential from <issuer> with <credential_data>
      When "Faber" sends a <request for proof> presentation to "Bob"
      And "Bob" makes the <presentation> of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer | credential_data      | request for proof            | presentation                |
         | Faber  | Data_BI_HealthValues | proof_request_health_consent | presentation_health_consent |


   @T001.5-RFC0037 @AIP10 @critical @AcceptanceTest @MobileTest @Indy
   Scenario Outline: Present Proof where the prover does not propose a presentation of the proof and is acknowledged
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Bob" has an issued credential from <issuer>
      And "Faber" and "Bob" have an existing connection
      When "Faber" sends a request for proof presentation to "Bob"
      And "Bob" makes the presentation of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer |
         | Acme   |
         | Faber  |

   @T003-RFC0037 @AIP10 @critical @AcceptanceTest @Schema_DriversLicense @Indy @ProofProposal
   Scenario Outline: Present Proof where the prover has proposed the presentation of proof in response to a presentation request and is acknowledged
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" have an existing connection
      And "Bob" has an issued credential from <issuer> with <credential_data>
      When "Faber" sends a <request_for_proof> presentation to "Bob"
      And "Bob" doesn’t want to reveal what was requested so makes a <presentation_proposal>
      And "Faber" agrees with the proposal so sends a <proposal_based_request_for_proof> presentation to "Bob"
      And "Bob" makes the <presentation> of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer | credential_data   | request_for_proof            | presentation_proposal   | proposal_based_request_for_proof | presentation                |
         | Acme   | Data_DL_MaxValues | proof_request_DL_address     | proposal_DL_age_over_19 | proof_request_DL_age_over_19     | presentation_DL_age_over_19 |
         | Faber  | Data_DL_MinValues | proof_request_DL_age_over_19 | proposal_DL_address     | proof_request_DL_address         | presentation_DL_address     |


   @T003.1-RFC0037 @AIP10 @critical @AcceptanceTest @Schema_DriversLicense @Schema_Health_ID @Indy @ProofProposal
   Scenario Outline: Present Proof where the prover has proposed the presentation of proof from a different credential in response to a presentation request and is acknowledged
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" have an existing connection
      And "Bob" has an issued credential from <issuer> with <credential_data>
      When "Faber" sends a <request_for_proof> presentation to "Bob"
      And "Bob" doesn’t want to reveal what was requested so makes a <presentation_proposal>
      And "Faber" agrees with the proposal so sends a <proposal_based_request_for_proof> presentation to "Bob"
      And "Bob" makes the <presentation> of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer | credential_data                | request_for_proof           | presentation_proposal  | proposal_based_request_for_proof | presentation               |
         | Acme   | Data_DL_MaxValues              | proof_request_DL_address    | proposal_Health_ID_Num | proof_request_Health_ID_Num      | presentation_Health_ID_Num |
         | Faber  | Data_HealthID_NormalizedValues | proof_request_Health_ID_Num | proposal_DL_address    | proof_request_DL_address         | presentation_DL_address    |

   # See issue #90 for when work on this test will resume - https://app.zenhub.com/workspaces/von---verifiable-organization-network-5adf53987ccbaa70597dbec0/issues/bcgov/aries-agent-test-harness/90
   @T004-RFC0037 @AIP10 @wip @critical @AcceptanceTest @NeedsReview
   Scenario Outline: Present Proof where the verifier and prover are connectionless, prover has proposed the presentation of proof, and is acknowledged
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" does not have a connection
      And "Bob" has an issued credential from <issuer>
      When "Faber" sends a request for proof presentation to "Bob"
      And "Bob" doesn’t want to reveal what was requested so makes a presentation proposal
      And "Faber" agrees to continue so sends a request for proof presentation
      And "Bob" makes the presentation of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer |
         | Acme   |
         | Faber  |

   @T005-RFC0037 @AIP10 @wip @normal @AcceptanceTest @ExceptionTest @Schema_DriversLicense @Indy @NeedsReview
   Scenario Outline: Present Proof where the verifier rejects the presentation of the proof
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" have an existing connection
      And "Bob" has an issued credential from <issuer> with <credential_data>
      When "Faber" sends a <request_for_proof> presentation to "Bob"
      And "Bob" makes the <presentation> of the proof incorrectly so "Faber" rejects the proof
      Then "Bob" has the proof unverified

      Examples:
         | issuer | credential_data   | request_for_proof        | presentation                      |
         | Acme   | Data_DL_MaxValues | proof_request_DL_address | presentation_DL_incorrect_address |


   @T006-RFC0037 @AIP10 @minor @AcceptanceTest @Schema_Health_ID @Indy @ProofProposal
   Scenario Outline: Present Proof where the prover starts with a proposal the presentation of proof and is acknowledged
      Given "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Faber" and "Bob" have an existing connection
      And "Bob" has an issued credential from <issuer> with <credential_data>
      When "Bob" makes a <presentation_proposal> to "Faber"
      And "Faber" sends a <request for proof> presentation to "Bob"
      And "Bob" makes the <presentation> of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

      Examples:
         | issuer | credential_data                | presentation_proposal  | request for proof           | presentation               |
         | Acme   | Data_HealthID_NormalizedValues | proposal_Health_ID_Num | proof_request_Health_ID_Num | presentation_Health_ID_Num |
