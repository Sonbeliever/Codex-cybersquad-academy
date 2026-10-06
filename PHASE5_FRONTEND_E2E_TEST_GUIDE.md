# Phase 5: CODEX ID & VERIFICATION SYSTEM - Frontend E2E Test Guide

**Project:** Codex Cybersquad Academy  
**Phase:** Phase 5 - Codex ID & Verification System  
**Test Date:** September 2026  
**Purpose:** Manual end-to-end testing documentation for Phase 5 frontend features

---

## Overview

This guide provides step-by-step instructions for manually testing the Phase 5 frontend features across all user roles (Student, Instructor, Admin). These tests complement the automated backend tests and verify the complete user workflows.

---

## Test Prerequisites

1. **Backend Running:** Flask development server must be running (`python run.py`)
2. **Database:** Database must be at migration head `283392952bc9`
3. **Test Users:** Create test accounts for each role:
   - Student: `student@test.com` / `password123`
   - Instructor: `instructor@test.com` / `password123`
   - Admin: `admin@test.com` / `password123`
4. **Browser:** Modern browser with camera support (Chrome, Firefox, Safari, Edge)
5. **HTTPS Required:** Camera access requires HTTPS or localhost

---

## Student Workflow Tests

### Test S1: View Digital Codex ID Card

**Objective:** Verify student can view their digital ID card with QR code and profile photo.

**Steps:**
1. Login as a student with an issued Codex ID
2. Navigate to "Codex ID" from the sidebar
3. Verify the following:
   - Codex ID card displays with CODEX branding
   - Profile photo displays (or initials placeholder if no photo)
   - Codex ID number is visible (format: CODEX-YYYY-NNNN)
   - Student name is displayed
   - Issue date is displayed
   - Status badge shows (active/suspended/revoked)
   - QR code is rendered in the QR section
   - Help text explains QR code usage

**Expected Result:** Digital ID card displays correctly with all information and QR code.

**Failure Criteria:**
- ID card does not display
- QR code does not render
- Profile photo/placeholder missing
- Information incorrect or missing

---

### Test S2: View Attendance History

**Objective:** Verify student can view their attendance history.

**Steps:**
1. Login as a student with attendance records
2. Navigate to "Attendance" from the sidebar
3. Verify the following:
   - Attendance list displays
   - Each record shows: session title, session type, scan date/time
   - Status badge shows (present/absent/excused)
   - Empty state displays if no records

**Expected Result:** Attendance history displays correctly with all records.

**Failure Criteria:**
- Attendance list does not display
- Records missing or incorrect
- Empty state not shown when appropriate

---

## Instructor Workflow Tests

### Test I1: Create Attendance Session

**Objective:** Verify instructor can create a new attendance session.

**Steps:**
1. Login as an instructor
2. Navigate to "Attendance Sessions" from the sidebar
3. Click "Create session" button
4. Fill in the form:
   - Title: "Test Workshop"
   - Session Type: "Workshop"
   - Description: "Test session for E2E testing"
   - Location: "Room 101"
   - Start Time: Select tomorrow's date and time
   - End Time: Leave optional
5. Click "Create Session"
6. Verify the following:
   - Success toast appears
   - Form closes
   - New session appears in the list with "draft" status
   - Session details are correct

**Expected Result:** Session created successfully and appears in the list.

**Failure Criteria:**
- Form does not open
- Validation errors prevent submission
- Session not created
- Session details incorrect

---

### Test I2: Activate Attendance Session

**Objective:** Verify instructor can activate a draft session for scanning.

**Steps:**
1. Login as an instructor with a draft session
2. Navigate to "Attendance Sessions"
3. Click "Activate" on a draft session
4. Verify the following:
   - Success toast appears
   - Session status changes to "active"
   - Session is now available for QR scanning

**Expected Result:** Session activated successfully.

**Failure Criteria:**
- Activate button not available
- Status does not change
- Error occurs

---

### Test I3: Close Attendance Session

**Objective:** Verify instructor can close an active session.

**Steps:**
1. Login as an instructor with an active session
2. Navigate to "Attendance Sessions"
3. Click "Close" on an active session
4. Verify the following:
   - Success toast appears
   - Session status changes to "closed"
   - Session is no longer available for scanning

**Expected Result:** Session closed successfully.

**Failure Criteria:**
- Close button not available
- Status does not change
- Error occurs

---

### Test I4: QR Scanner - Verification Mode

**Objective:** Verify instructor can verify student QR codes without recording attendance.

**Steps:**
1. Login as an instructor
2. Navigate to "QR Scanner" from the sidebar
3. Click "Start Camera" (grant camera permission if prompted)
4. Select "Verify only" mode
5. Point camera at a student's QR code (use test QR from student's Codex ID)
6. Verify the following:
   - Camera activates and displays video feed
   - QR code is detected and scanned
   - Student information displays (Codex ID, status, issue date)
   - Status badge shows correct color (green for active, orange for suspended, red for revoked)
   - "Scan Again" button appears
7. Click "Scan Again" to reset

**Expected Result:** QR code verified successfully with student information displayed.

**Failure Criteria:**
- Camera does not start
- QR code not detected
- Information incorrect
- Scan does not pause after successful scan

---

### Test I5: QR Scanner - Attendance Recording Mode

**Objective:** Verify instructor can record attendance using QR codes.

**Steps:**
1. Login as an instructor with an active session
2. Navigate to "QR Scanner"
3. Click "Start Camera"
4. Select an active session from the dropdown
5. Select "Record attendance" mode
6. Point camera at a student's QR code
7. Verify the following:
   - QR code is detected and scanned
   - Attendance recorded confirmation displays
   - Student Codex ID shows
   - Status shows "PRESENT"
   - Scan timestamp displays
   - "Scan Again" button appears
8. Click "Scan Again" and scan the same QR code again
9. Verify duplicate protection:
   - Error message: "Already recorded for this session"

**Expected Result:** Attendance recorded successfully with duplicate protection.

**Failure Criteria:**
- Attendance not recorded
- Duplicate scan not prevented
- Error handling incorrect

---

### Test I6: QR Scanner - Suspended ID Scenario

**Objective:** Verify scanner handles suspended student IDs correctly.

**Steps:**
1. Admin suspends a student's Codex ID
2. Login as an instructor
3. Navigate to "QR Scanner"
4. Select "Record attendance" mode with an active session
5. Scan the suspended student's QR code
6. Verify the following:
   - Error message: "Student ID is suspended - attendance not recorded"
   - No attendance record created

**Expected Result:** Suspended ID correctly rejected with appropriate error message.

**Failure Criteria:**
- Attendance recorded despite suspension
- Error message unclear or missing

---

### Test I7: QR Scanner - Revoked ID Scenario

**Objective:** Verify scanner handles revoked student IDs correctly.

**Steps:**
1. Admin revokes a student's Codex ID
2. Login as an instructor
3. Navigate to "QR Scanner"
4. Select "Record attendance" mode with an active session
5. Scan the revoked student's QR code
6. Verify the following:
   - Error message: "Student ID is revoked - attendance not recorded"
   - No attendance record created

**Expected Result:** Revoked ID correctly rejected with appropriate error message.

**Failure Criteria:**
- Attendance recorded despite revocation
- Error message unclear or missing

---

### Test I8: QR Scanner - No Active Session Scenario

**Objective:** Verify scanner behavior when no session is selected.

**Steps:**
1. Login as an instructor
2. Navigate to "QR Scanner"
3. Select "Record attendance" mode
4. Leave session dropdown empty
5. Scan a student's QR code
6. Verify the following:
   - Falls back to verification mode
   - Student information displays
   - No attendance recorded

**Expected Result:** Scanner correctly falls back to verification when no session selected.

**Failure Criteria:**
- Error occurs
- Incorrect behavior

---

## Admin Workflow Tests

### Test A1: Issue Codex Student ID

**Objective:** Verify admin can issue a new Codex ID to a student.

**Steps:**
1. Login as an admin
2. Navigate to "Codex IDs" from the sidebar
3. Click "Issue ID" button
4. Enter a valid student email address
5. Click "Issue ID"
6. Verify the following:
   - Success toast appears
   - Form closes
   - New ID appears in the list
   - ID format is correct (CODEX-YYYY-NNNN)
   - Status is "active"
   - Student name is displayed

**Expected Result:** Codex ID issued successfully with correct format and status.

**Failure Criteria:**
- Form does not open
- Validation errors
- ID not issued
- Format incorrect

---

### Test A2: Suspend Codex Student ID

**Objective:** Verify admin can suspend a student ID.

**Steps:**
1. Login as an admin
2. Navigate to "Codex IDs"
3. Click "Suspend" on an active ID
4. Verify the following:
   - Success toast appears
   - Status changes to "suspended"
   - Status badge color changes to orange

**Expected Result:** ID suspended successfully.

**Failure Criteria:**
- Suspend button not available
- Status does not change
- Error occurs

---

### Test A3: Activate Suspended Codex ID

**Objective:** Verify admin can reactivate a suspended ID.

**Steps:**
1. Login as an admin
2. Navigate to "Codex IDs"
3. Click "Activate" on a suspended ID
4. Verify the following:
   - Success toast appears
   - Status changes to "active"
   - Status badge color changes to green

**Expected Result:** ID reactivated successfully.

**Failure Criteria:**
- Activate button not available
- Status does not change
- Error occurs

---

### Test A4: View All Attendance Sessions

**Objective:** Verify admin can view all attendance sessions across instructors.

**Steps:**
1. Login as an admin
2. Navigate to "All Sessions" from the sidebar
3. Verify the following:
   - All sessions from all instructors display
   - Session details include: title, type, date, creator, record count
   - Status badges show correct colors
   - Action buttons available (activate, close, view)

**Expected Result:** All sessions display correctly with complete information.

**Failure Criteria:**
- Sessions not displayed
- Information missing
- Actions not available

---

### Test A5: Admin QR Scanner Access

**Objective:** Verify admin can access QR scanner with full permissions.

**Steps:**
1. Login as an admin
2. Navigate to "QR Scanner" from the sidebar
3. Verify the following:
   - Scanner loads
   - All sessions (not just own) appear in dropdown
   - Verification and recording modes work
   - Admin can scan for any session

**Expected Result:** Admin has full scanner access to all sessions.

**Failure Criteria:**
- Scanner not accessible
- Limited session access
- Errors occur

---

## Cross-Role Workflow Tests

### Test X1: Student ID Issuance to Attendance Recording

**Objective:** Verify complete workflow from ID issuance to attendance recording.

**Steps:**
1. Admin issues a Codex ID to a student
2. Student logs in and views their Codex ID (verify QR code displays)
3. Instructor creates and activates an attendance session
4. Instructor uses QR scanner to record student attendance
5. Student logs in and views attendance history
6. Verify the following:
   - ID issued correctly
   - QR code displays for student
   - Session created and activated
   - Attendance recorded successfully
   - Attendance appears in student's history

**Expected Result:** Complete end-to-end workflow succeeds.

**Failure Criteria:**
- Any step fails
- Data not propagated correctly

---

## UI Quality Verification

### Test U1: Responsive Design - Desktop

**Objective:** Verify UI displays correctly on desktop screens.

**Steps:**
1. Open application on desktop browser (1920x1080 or similar)
2. Navigate through all Phase 5 pages (Codex ID, Attendance, Attendance Sessions, QR Scanner, Codex IDs, All Sessions)
3. Verify the following:
   - Layout is balanced and not cramped
   - Text is readable
   - Buttons are appropriately sized
   - Scanner layout uses two-column grid
   - Forms are properly aligned

**Expected Result:** UI displays correctly on desktop.

**Failure Criteria:**
- Layout issues
- Overlapping elements
- Poor readability

---

### Test U2: Responsive Design - Tablet

**Objective:** Verify UI adapts to tablet screens.

**Steps:**
1. Open application on tablet (768px - 1024px)
2. Navigate through Phase 5 pages
3. Verify the following:
   - Sidebar remains accessible
   - Scanner layout adapts (may stack vertically)
   - Forms remain usable
   - No horizontal scrolling required

**Expected Result:** UI adapts correctly to tablet.

**Failure Criteria:**
- Layout breaks
- Elements overlapping
- Unusable interface

---

### Test U3: Responsive Design - Mobile

**Objective:** Verify UI adapts to mobile screens.

**Steps:**
1. Open application on mobile (375px - 480px)
2. Navigate through Phase 5 pages
3. Verify the following:
   - Sidebar collapses to mobile menu
   - Scanner layout stacks vertically
   - Forms remain usable with touch targets
   - QR code display remains readable
   - No horizontal scrolling

**Expected Result:** UI adapts correctly to mobile.

**Failure Criteria:**
- Layout breaks
- Touch targets too small
- Unusable interface

---

### Test U4: Visual Consistency

**Objective:** Verify Phase 5 UI matches Codex Academy visual language.

**Steps:**
1. Navigate through Phase 5 pages
2. Verify the following:
   - Colors match brand (navy, green, muted)
   - Typography uses Manrope for headings, DM Sans for body
   - Status badges use correct colors (green=active, orange=suspended, red=revoked)
   - Codex ID card matches design spec
   - Scanner controls are styled consistently
   - Forms match existing form styling

**Expected Result:** Visual consistency maintained throughout.

**Failure Criteria:**
- Inconsistent colors
- Wrong fonts
- Mismatched styling

---

### Test U5: Accessibility

**Objective:** Verify basic accessibility features.

**Steps:**
1. Navigate through Phase 5 pages
2. Verify the following:
   - Form labels are associated with inputs
   - Buttons have descriptive text
   - Status badges have text (not just color)
   - Error messages are clear and actionable
   - Keyboard navigation works for forms

**Expected Result:** Basic accessibility features present.

**Failure Criteria:**
- Missing labels
- Unclear controls
- Poor keyboard navigation

---

## Test Results Template

Use this template to record test results:

| Test ID | Test Name | Status | Notes | Date |
|---------|-----------|--------|-------|------|
| S1 | [Test Name] | PASS/FAIL | [Observations] | [Date] |
| S2 | [Test Name] | PASS/FAIL | [Observations] | [Date] |
| ... | ... | ... | ... | ... |

---

## Known Limitations

1. **Camera Testing:** Actual camera functionality requires a device with a camera and HTTPS/localhost environment. Testing in environments without camera access will be limited to UI verification only.

2. **Node.js/npm Unavailable:** Frontend build verification cannot be performed in the current environment due to Node.js/npm not being installed. Static code inspection was performed instead.

3. **Profile Photo Display:** Profile photo display depends on the `User.profile_image` field being populated. Without actual photo uploads, only the fallback placeholder can be tested.

---

## Sign-off

**Tester:** __________________________  
**Date:** __________________________  
**Overall Status:** PASS / FAIL / PARTIAL  
**Comments:** __________________________
