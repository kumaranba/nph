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
      tags
    }
  }
`;

// Patients carrying the given tags. `match` is ANY (default) or ALL.
export const PATIENTS_BY_TAGS = gql`
  query PatientsByTags($tags: [String!]!, $match: TagMatchEnum) {
    patientsByTags(tags: $tags, match: $match) {
      id
      patientId
      name
      guardianName
      guardianPhone
      admissionDate
      room
      bed
      feeStatus
      tags
    }
  }
`;

// Tag typeahead. Empty query returns the most-used tags.
export const TAG_SUGGESTIONS = gql`
  query TagSuggestions($query: String, $category: TagCategoryEnum) {
    tagSuggestions(query: $query, category: $category) {
      id
      name
      label
      category
      patientCount
    }
  }
`;

export const ADD_PATIENT_TAGS = gql`
  mutation AddPatientTags($patientId: ID!, $tags: [String!]!, $category: TagCategoryEnum) {
    addPatientTags(patientId: $patientId, tags: $tags, category: $category) {
      id
      tags { id name label category }
    }
  }
`;

export const REMOVE_PATIENT_TAG = gql`
  mutation RemovePatientTag($patientId: ID!, $tag: String!) {
    removePatientTag(patientId: $patientId, tag: $tag) {
      id
      tags { id name label category }
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
      openingBalance
      totalDueNow
      daysUntilDue
    }
  }
`;

// Active patients who currently owe money (past dues included), highest first.
export const PENDING_DUES_LIST = gql`
  query PendingDuesList {
    pendingDuesList {
      id
      patientId
      name
      gender
      room
      admissionDate
      currentFees
      totalPendingDues
      contact
      place
    }
  }
`;

// Discharged admissions — optional tag filter, sorted by discharge date.
export const DISCHARGED_LIST = gql`
  query DischargedList($tag: String, $sortDesc: Boolean) {
    dischargedList(tag: $tag, sortDesc: $sortDesc) {
      id
      patientId
      name
      admissionDate
      dischargeDate
      dischargeType
      room
      tags
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

// Admit an existing patient (new admission / re-admission after discharge).
export const READMIT_PATIENT = gql`
  mutation ReadmitPatient(
    $patientId: ID!
    $admissionDate: Date!
    $monthlyFee: Decimal!
    $bedId: ID
  ) {
    readmitPatient(
      patientId: $patientId
      admissionDate: $admissionDate
      monthlyFee: $monthlyFee
      bedId: $bedId
    ) {
      id
      status
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
      dateOfBirth
      gender
      diagnosis
      foodPreference
      isAlive
      dateOfExpiry
      photoUrl
      guardianName
      guardianPhone
      admittingDoctor
      place
      contactConsent
      doNotContact
      createdAt
      tags { id name label category }
      admissions {
        id
        status
        admissionDate
        dischargeDate
        dischargeType
        monthlyFee
        creditBalance
        openingBalance
        openingBalanceDue
        nextFeeCycleDate
        activeFee {
          id
          amount
          effectiveFrom
        }
        effectiveFee {
          id
          amount
          effectiveFrom
        }
        outstandingDue
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

// ADMIN-only fields (Aadhar). Kept out of the shared PATIENT query so a
// non-admin viewing a profile doesn't hit the Aadhar permission error.
export const PATIENT_AADHAR = gql`
  query PatientAadhar($pk: ID!) {
    patient(pk: $pk) {
      id
      aadharNumber
      aadharScanUrl
    }
  }
`;

export const UPDATE_PATIENT = gql`
  mutation UpdatePatient($patientId: ID!, $input: UpdatePatientInput!) {
    updatePatient(patientId: $patientId, input: $input) {
      id
      name
      age
      dateOfBirth
      gender
      diagnosis
      admittingDoctor
      guardianName
      guardianPhone
      place
      foodPreference
      isAlive
      dateOfExpiry
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
  mutation LogPayment(
    $invoiceId: ID!
    $amount: Decimal!
    $paidOn: Date!
    $accountId: ID
  ) {
    logPayment(
      invoiceId: $invoiceId
      amount: $amount
      paidOn: $paidOn
      accountId: $accountId
    ) {
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
export const PAYMENT_ACCOUNTS = gql`
  query PaymentAccounts {
    paymentAccounts {
      id
      name
    }
  }
`;

// A patient's account ledger (invoices vs payments) over an optional range.
export const ACCOUNT_STATEMENT = gql`
  query AccountStatement($pid: ID!, $from: Date, $to: Date) {
    accountStatement(patientId: $pid, dateFrom: $from, dateTo: $to) {
      patientName
      patientCode
      openingBalance
      closingBalance
      totalDebits
      totalCredits
      lines {
        date
        description
        debit
        credit
        balance
      }
    }
  }
`;

// Payments received in a date range (each a receipt), newest first.
export const PAYMENT_RECEIPTS = gql`
  query PaymentReceipts($from: Date, $to: Date) {
    paymentReceipts(dateFrom: $from, dateTo: $to) {
      id
      patientPk
      patientName
      patientCode
      paidOn
      amount
      feesAmount
      chargesAmount
      account {
        name
      }
    }
  }
`;

export const RECORD_PATIENT_PAYMENT = gql`
  mutation RecordPatientPayment(
    $patientId: ID!
    $feesAmount: Decimal!
    $chargesAmount: Decimal!
    $paidOn: Date!
    $accountId: ID
  ) {
    recordPatientPayment(
      patientId: $patientId
      feesAmount: $feesAmount
      chargesAmount: $chargesAmount
      paidOn: $paidOn
      accountId: $accountId
    ) {
      patientId
      receiptId
      totalRecorded
      feesAmount
      chargesAmount
      account
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

export const DISCHARGE_PREVIEW = gql`
  query DischargePreview($admissionId: ID!, $dischargeDate: Date) {
    dischargePreview(admissionId: $admissionId, dischargeDate: $dischargeDate) {
      dischargeDate
      hasCurrentCycle
      cycleStart
      cycleEnd
      fullFee
      daysInPeriod
      daysStayed
      proratedFee
      cancelledFee
      feesDue
      chargesDue
      totalDueNow
      lines {
        label
        kind
        amount
      }
    }
  }
`;

export const DISCHARGE_PATIENT = gql`
  mutation DischargePatient(
    $admissionId: ID!
    $dischargeDate: Date
    $feesPaid: Decimal
    $chargesPaid: Decimal
    $accountId: ID
    $refundAmount: Decimal
    $medicationAmount: Decimal
    $medicationNote: String
  ) {
    dischargePatient(
      admissionId: $admissionId
      dischargeDate: $dischargeDate
      feesPaid: $feesPaid
      chargesPaid: $chargesPaid
      accountId: $accountId
      refundAmount: $refundAmount
      medicationAmount: $medicationAmount
      medicationNote: $medicationNote
    ) {
      refundAmount
      admission {
        id
        status
        dischargeDate
      }
    }
  }
`;

// --- PRM: inquiries -------------------------------------------------------

export const INQUIRIES = gql`
  query Inquiries($status: InquiryStatusEnum, $search: String) {
    inquiries(status: $status, search: $search) {
      id
      name
      phone
      source
      status
      lostReason
      contactConsent
      doNotContact
      consultedOn
      notes
      createdAt
      assignedTo {
        id
        email
      }
      referrer {
        id
        name
      }
      patient {
        id
        patientId
        name
      }
    }
  }
`;

export const OP_CONSULT_WORKLIST = gql`
  query OpConsultWorklist {
    opConsultWorklist {
      id
      name
      phone
      source
      status
      lostReason
      contactConsent
      doNotContact
      consultedOn
      notes
      createdAt
      assignedTo {
        id
        email
      }
      patient {
        id
        patientId
        name
      }
    }
  }
`;

export const SET_CONSULTED = gql`
  mutation SetConsulted($id: ID!, $consultedOn: Date) {
    setConsulted(inquiryId: $id, consultedOn: $consultedOn) {
      id
      consultedOn
    }
  }
`;

export const PRO_USERS = gql`
  query ProUsers {
    proUsers {
      id
      email
    }
  }
`;

export const CREATE_INQUIRY = gql`
  mutation CreateInquiry($data: CreateInquiryInput!) {
    createInquiry(data: $data) {
      id
    }
  }
`;

export const UPDATE_INQUIRY = gql`
  mutation UpdateInquiry(
    $id: ID!
    $name: String
    $phone: String
    $notes: String
    $source: InquirySourceEnum
  ) {
    updateInquiry(
      inquiryId: $id
      name: $name
      phone: $phone
      notes: $notes
      source: $source
    ) {
      id
      name
      phone
      notes
      source
    }
  }
`;

// Public, unauthenticated: the website enquiry form.
export const SUBMIT_WEB_ENQUIRY = gql`
  mutation SubmitWebEnquiry($data: WebEnquiryInput!) {
    submitWebEnquiry(data: $data) {
      ok
      message
    }
  }
`;

export const UPDATE_INQUIRY_STATUS = gql`
  mutation UpdateInquiryStatus(
    $id: ID!
    $status: InquiryStatusEnum!
    $lostReason: LostReasonEnum
    $lostReasonNote: String
  ) {
    updateInquiryStatus(
      inquiryId: $id
      status: $status
      lostReason: $lostReason
      lostReasonNote: $lostReasonNote
    ) {
      id
      status
      lostReason
    }
  }
`;

export const ASSIGN_INQUIRY = gql`
  mutation AssignInquiry($id: ID!, $userId: ID!) {
    assignInquiry(inquiryId: $id, userId: $userId) {
      id
      assignedTo {
        id
        email
      }
    }
  }
`;

export const LINK_INQUIRY_TO_PATIENT = gql`
  mutation LinkInquiryToPatient($id: ID!, $patientId: ID!) {
    linkInquiryToPatient(inquiryId: $id, patientId: $patientId) {
      id
      status
      patient {
        id
        patientId
        name
      }
    }
  }
`;

// --- PRM: follow-ups ------------------------------------------------------

export const FOLLOW_UPS = gql`
  query FollowUps($patientId: ID!) {
    followUps(patientId: $patientId) {
      id
      note
      followUpDate
      isDone
      admission {
        id
      }
    }
  }
`;

export const DUE_FOLLOW_UPS = gql`
  query DueFollowUps {
    dueFollowUps {
      id
      note
      followUpDate
      kind
      subjectName
      patient {
        id
        patientId
        name
      }
      inquiry {
        id
        name
      }
    }
  }
`;

export const DUE_FOLLOW_UP_COUNT = gql`
  query DueFollowUpCount {
    dueFollowUpCount
  }
`;

export const CREATE_FOLLOW_UP = gql`
  mutation CreateFollowUp($data: CreateFollowUpInput!) {
    createFollowUp(data: $data) {
      id
      note
      followUpDate
      isDone
    }
  }
`;

export const MARK_FOLLOW_UP_DONE = gql`
  mutation MarkFollowUpDone($id: ID!) {
    markFollowUpDone(followUpId: $id) {
      id
      isDone
    }
  }
`;

// --- Staff registry -------------------------------------------------------

export const STAFF_LIST = gql`
  query StaffList(
    $includeInactive: Boolean
    $designation: StaffDesignationEnum
    $search: String
  ) {
    staffList(
      includeInactive: $includeInactive
      designation: $designation
      search: $search
    ) {
      id
      staffCode
      name
      designation
      gender
      phone
      isActive
      joinedOn
    }
  }
`;

export const CREATE_STAFF = gql`
  mutation CreateStaff($data: CreateStaffInput!) {
    createStaff(data: $data) {
      id
    }
  }
`;

export const UPDATE_STAFF = gql`
  mutation UpdateStaff($id: ID!, $data: UpdateStaffInput!) {
    updateStaff(staffId: $id, data: $data) {
      id
      name
      designation
      phone
      isActive
      joinedOn
    }
  }
`;

// --- Staff attendance -----------------------------------------------------

export const ATTENDANCE_ROSTER = gql`
  query AttendanceRoster($date: Date!) {
    attendanceRoster(date: $date) {
      staff {
        id
        staffCode
        name
        designation
      }
      status
    }
  }
`;

export const BULK_MARK_ATTENDANCE = gql`
  mutation BulkMarkAttendance($date: Date!, $entries: [AttendanceEntryInput!]!) {
    bulkMarkAttendance(date: $date, entries: $entries) {
      staff {
        id
      }
      status
    }
  }
`;

export const ATTENDANCE_SUMMARY = gql`
  query AttendanceSummary($staffId: ID!, $from: Date, $to: Date) {
    attendanceSummary(staffId: $staffId, dateFrom: $from, dateTo: $to) {
      staff {
        id
        name
        staffCode
      }
      present
      absent
      leave
      halfDay
      markedDays
    }
  }
`;

// --- Food vendor rate -----------------------------------------------------

export const FOOD_RATES = gql`
  query FoodRates {
    currentFoodRate {
      id
      amount
      effectiveFrom
    }
    foodRates {
      id
      amount
      effectiveFrom
      note
      createdBy {
        email
      }
    }
  }
`;

export const SET_FOOD_RATE = gql`
  mutation SetFoodRate($amount: Decimal!, $effectiveFrom: Date, $note: String) {
    setFoodRate(amount: $amount, effectiveFrom: $effectiveFrom, note: $note) {
      id
    }
  }
`;

// --- Food reports ---------------------------------------------------------

export const FOOD_VENDOR_LIST = gql`
  query FoodVendorList($from: Date!, $to: Date!) {
    foodVendorList(dateFrom: $from, dateTo: $to) {
      dateFrom
      dateTo
      totalPatientDays
      totalAmount
      rows {
        day
        patients
        rate
        amount
      }
    }
  }
`;

export const PATIENT_FOOD_REPORT = gql`
  query PatientFoodReport($month: String) {
    patientFoodReport(month: $month) {
      month
      rate
      grandTotalDays
      grandTotalAmount
      groups {
        key
        label
        totalDays
        totalAmount
        rows {
          patientPk
          patientCode
          name
          days
          rate
          amount
        }
      }
    }
  }
`;

// --- Canteen: staff monthly meal rate -------------------------------------

export const STAFF_MEAL_RATES = gql`
  query StaffMealRates {
    currentStaffMealRate {
      id
      amount
      effectiveFrom
    }
    staffMealRates {
      id
      amount
      effectiveFrom
      note
      createdBy {
        email
      }
    }
  }
`;

export const SET_STAFF_MEAL_RATE = gql`
  mutation SetStaffMealRate($amount: Decimal!, $effectiveFrom: Date, $note: String) {
    setStaffMealRate(amount: $amount, effectiveFrom: $effectiveFrom, note: $note) {
      id
    }
  }
`;

// --- Canteen meal count report --------------------------------------------

export const CANTEEN_REPORT = gql`
  query CanteenReport($month: String) {
    canteenReport(month: $month) {
      month
      dailyRate
      staffMonthlyRate
      activeStaff
      hasOther
      patientCost
      staffCost
      grandTotalCost
      totals {
        malePatients
        femalePatients
        otherPatients
        maleStaff
        femaleStaff
        otherStaff
        patientDays
        staffDays
        total
      }
      days {
        day
        dow
        isSplit
        malePatients
        malePatientsNonveg
        femalePatients
        femalePatientsNonveg
        otherPatients
        otherPatientsNonveg
        maleStaff
        femaleStaff
        otherStaff
        total
      }
    }
  }
`;

// --- PRM: activity timeline (R2) ------------------------------------------

export const ACTIVITIES = gql`
  query Activities($inquiryId: ID, $patientId: ID) {
    activities(inquiryId: $inquiryId, patientId: $patientId) {
      id
      type
      body
      outcome
      createdAt
      createdBy {
        email
      }
    }
  }
`;

export const ADD_ACTIVITY = gql`
  mutation AddActivity(
    $type: ActivityKindEnum!
    $body: String!
    $inquiryId: ID
    $patientId: ID
    $outcome: String
  ) {
    addActivity(
      type: $type
      body: $body
      inquiryId: $inquiryId
      patientId: $patientId
      outcome: $outcome
    ) {
      id
    }
  }
`;

// --- PRM: contact consent / do-not-contact (R3) ---------------------------

export const SET_CONTACT_CONSENT = gql`
  mutation SetContactConsent(
    $consent: ConsentStatusEnum!
    $doNotContact: Boolean!
    $inquiryId: ID
    $patientId: ID
  ) {
    setContactConsent(
      consent: $consent
      doNotContact: $doNotContact
      inquiryId: $inquiryId
      patientId: $patientId
    ) {
      contactConsent
      doNotContact
    }
  }
`;

// --- PRM: analytics dashboard (Phase 2) -----------------------------------

export const PRM_ANALYTICS = gql`
  query PrmAnalytics($dateFrom: Date, $dateTo: Date) {
    prmAnalytics(dateFrom: $dateFrom, dateTo: $dateTo) {
      totalLeads
      converted
      lost
      open
      conversionRate
      avgDaysToConvert
      bySource {
        source
        leads
        converted
        conversionRate
      }
      byStage {
        stage
        count
      }
      lostReasons {
        reason
        count
      }
      monthly {
        month
        leads
      }
      byPro {
        email
        owned
        converted
      }
    }
  }
`;

// --- PRM: referral sources ------------------------------------------------

export const REFERRERS = gql`
  query Referrers($includeInactive: Boolean) {
    referrers(includeInactive: $includeInactive) {
      id
      name
      kind
      organization
      phone
      email
      notes
      isActive
    }
  }
`;

export const REFERRER_STATS = gql`
  query ReferrerStats {
    referrerStats {
      referrer {
        id
        name
        kind
        organization
      }
      leads
      converted
      conversionRate
    }
  }
`;

export const CREATE_REFERRER = gql`
  mutation CreateReferrer($data: CreateReferrerInput!) {
    createReferrer(data: $data) {
      id
    }
  }
`;

export const UPDATE_REFERRER = gql`
  mutation UpdateReferrer($id: ID!, $data: UpdateReferrerInput!) {
    updateReferrer(referrerId: $id, data: $data) {
      id
      isActive
    }
  }
`;

export const SET_INQUIRY_REFERRER = gql`
  mutation SetInquiryReferrer($id: ID!, $referrerId: ID) {
    setInquiryReferrer(inquiryId: $id, referrerId: $referrerId) {
      id
      referrer {
        id
        name
      }
    }
  }
`;

// --- PRM: duplicate detection & merge -------------------------------------

export const DUPLICATE_INQUIRY_GROUPS = gql`
  query DuplicateInquiryGroups {
    duplicateInquiryGroups {
      key
      inquiries {
        id
        name
        phone
        source
        status
        consultedOn
        createdAt
        assignedTo {
          id
          email
        }
        patient {
          id
          patientId
          name
        }
      }
    }
  }
`;

export const MERGE_INQUIRIES = gql`
  mutation MergeInquiries($primaryId: ID!, $duplicateId: ID!) {
    mergeInquiries(primaryId: $primaryId, duplicateId: $duplicateId) {
      id
    }
  }
`;
