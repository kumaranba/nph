import { gql } from "@apollo/client";

export const LOGIN = gql`
  mutation Login($email: String!, $password: String!) {
    login(email: $email, password: $password) {
      accessToken
      refreshToken
    }
  }
`;

export const ME = gql`
  query Me {
    me {
      id
      email
      role
    }
  }
`;

export const SEARCH_PATIENTS = gql`
  query SearchPatients($query: String!) {
    searchPatients(query: $query) {
      id
      patientId
      name
      guardianName
      guardianPhone
      admissionDate
      room
      bed
      feeStatus
    }
  }
`;

// Patients whose next billing cycle date falls within `withinDays` of today.
// Pass null to use the server's feeDueWarningDays default.
export const FEES_DUE_LIST = gql`
  query FeesDueList($withinDays: Int) {
    feesDueList(withinDays: $withinDays) {
      id
      patientId
      name
      room
      dueDate
      amountDue
      daysUntilDue
    }
  }
`;

// Only vacant beds — used to populate the admission form's bed picker.
export const VACANT_BEDS = gql`
  query VacantBeds {
    beds(status: "VACANT") {
      id
      label
      room {
        id
        name
      }
    }
  }
`;

export const CREATE_ADMISSION = gql`
  mutation CreateAdmission($input: CreateAdmissionInput!) {
    createAdmission(input: $input) {
      id
      status
      patient {
        id
        patientId
        name
      }
      bed {
        id
        label
        status
      }
    }
  }
`;

// A single patient (with admissions), used by the patient profile page.
export const PATIENT = gql`
  query Patient($pk: ID!) {
    patient(pk: $pk) {
      id
      patientId
      name
      age
      diagnosis
      guardianName
      guardianPhone
      admittingDoctor
      createdAt
      admissions {
        id
        status
        admissionDate
        monthlyFee
        creditBalance
        nextFeeCycleDate
        activeFee {
          id
          amount
          effectiveFrom
        }
        hasOutstandingDues
        outstandingInvoiceCount
        bed {
          id
          label
          room {
            id
            name
          }
        }
        additionalCharges {
          id
          category
          amount
          chargeDate
          description
        }
      }
    }
  }
`;

export const CREATE_CHARGE = gql`
  mutation CreateCharge(
    $admissionId: ID!
    $category: ChargeCategoryEnum!
    $amount: Decimal!
    $chargeDate: Date!
    $description: String
  ) {
    createCharge(
      admissionId: $admissionId
      category: $category
      amount: $amount
      chargeDate: $chargeDate
      description: $description
    ) {
      id
      category
      amount
      chargeDate
      description
    }
  }
`;

export const DELETE_CHARGE = gql`
  mutation DeleteCharge($chargeId: ID!) {
    deleteCharge(chargeId: $chargeId)
  }
`;

export const VITAL_HISTORY = gql`
  query VitalHistory(
    $patientId: ID!
    $dateFrom: Date
    $dateTo: Date
    $types: [String!]
  ) {
    vitalHistory(
      patientId: $patientId
      dateFrom: $dateFrom
      dateTo: $dateTo
      types: $types
    ) {
      id
      recordedAt
      session
      bpSystolic
      bpDiastolic
      pulse
      temperature
      spo2
      weight
      hasFlag
      flaggedVitals
    }
  }
`;

export const USERS = gql`
  query Users {
    users {
      id
      email
      role
      isActive
      dateJoined
    }
  }
`;

export const CREATE_USER = gql`
  mutation CreateUser($email: String!, $password: String!, $role: UserRoleEnum!) {
    createUser(email: $email, password: $password, role: $role) {
      id
      email
      role
      isActive
    }
  }
`;

export const DEACTIVATE_USER = gql`
  mutation DeactivateUser($userId: ID!) {
    deactivateUser(userId: $userId) {
      id
      isActive
    }
  }
`;

export const SYSTEM_SETTINGS = gql`
  query SystemSettings {
    systemSettings {
      feeDueWarningDays
      vitalsThresholds {
        vitalType
        belowThreshold
        aboveThreshold
      }
    }
  }
`;

export const UPDATE_SETTINGS = gql`
  mutation UpdateSettings(
    $feeDueWarningDays: Int
    $thresholds: [VitalsThresholdInput!]
  ) {
    updateSettings(
      feeDueWarningDays: $feeDueWarningDays
      thresholds: $thresholds
    ) {
      feeDueWarningDays
      vitalsThresholds {
        vitalType
        belowThreshold
        aboveThreshold
      }
    }
  }
`;

export const VITALS_THRESHOLDS = gql`
  query VitalsThresholds {
    vitalsThresholds {
      vitalType
      belowThreshold
      aboveThreshold
    }
  }
`;

export const CREATE_VITAL_READING = gql`
  mutation CreateVitalReading(
    $admissionId: ID!
    $session: VitalSessionEnum!
    $bpSystolic: Int!
    $bpDiastolic: Int!
    $pulse: Int!
    $temperature: Decimal!
    $spo2: Int!
    $weight: Decimal
    $notes: String
  ) {
    createVitalReading(
      admissionId: $admissionId
      session: $session
      bpSystolic: $bpSystolic
      bpDiastolic: $bpDiastolic
      pulse: $pulse
      temperature: $temperature
      spo2: $spo2
      weight: $weight
      notes: $notes
    ) {
      id
      hasFlag
      flaggedVitals
      recordedAt
    }
  }
`;

// A single invoice for a patient + billing month ("YYYY-MM").
export const INVOICE = gql`
  query Invoice($patientId: ID!, $period: String!) {
    invoice(patientId: $patientId, period: $period) {
      id
      billingPeriodStart
      billingPeriodEnd
      baseFee
      refundAmount
      totalDue
      amountPaid
      balanceDue
      status
      admission {
        id
        patient {
          id
          patientId
          name
        }
      }
      additionalCharges {
        id
        category
        amount
        chargeDate
        description
      }
      payments {
        id
        amount
        paidOn
      }
    }
  }
`;

export const LOG_PAYMENT = gql`
  mutation LogPayment($invoiceId: ID!, $amount: Decimal!, $paidOn: Date!) {
    logPayment(invoiceId: $invoiceId, amount: $amount, paidOn: $paidOn) {
      id
      status
      amountPaid
      balanceDue
    }
  }
`;

export const FEE_HISTORY = gql`
  query FeeHistory($patientId: ID!) {
    feeHistory(patientId: $patientId) {
      id
      amount
      effectiveFrom
      isActive
      reason
      createdAt
      createdBy {
        email
      }
      admission {
        id
        admissionDate
      }
    }
  }
`;

export const CHANGE_FEE = gql`
  mutation ChangeFee(
    $admissionId: ID!
    $amount: Decimal!
    $reason: String!
    $effectiveFrom: Date
    $override: Boolean
  ) {
    changeFee(
      admissionId: $admissionId
      amount: $amount
      reason: $reason
      effectiveFrom: $effectiveFrom
      override: $override
    ) {
      id
      amount
      effectiveFrom
      isActive
    }
  }
`;

// Record a patient-level payment (clears outstanding + advances future months).
export const RECORD_PATIENT_PAYMENT = gql`
  mutation RecordPatientPayment(
    $patientId: ID!
    $amount: Decimal!
    $paidOn: Date!
  ) {
    recordPatientPayment(
      patientId: $patientId
      amount: $amount
      paidOn: $paidOn
    ) {
      patientId
      totalRecorded
      invoicesPaid
      creditAdded
      creditBalance
      allocations {
        period
        amount
      }
    }
  }
`;

export const DISCHARGE_PATIENT = gql`
  mutation DischargePatient($admissionId: ID!, $refundAmount: Decimal) {
    dischargePatient(admissionId: $admissionId, refundAmount: $refundAmount) {
      hasOutstandingDues
      outstandingInvoiceCount
      refundAmount
      admission {
        id
        status
        dischargeDate
      }
    }
  }
`;
