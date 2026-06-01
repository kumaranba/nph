from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Room, Bed, Patient, Admission,
    Invoice, Payment, AdditionalCharge, VitalReading, VitalsThreshold,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'role', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('email',)
    ordering = ('email',)
    fieldsets = (
        (None,          {'fields': ('email', 'password')}),
        ('Role',        {'fields': ('role',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates',       {'fields': ('date_joined', 'last_login')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'role', 'password1', 'password2'),
        }),
    )
    # BaseUserAdmin uses 'username'; override with our identifier
    filter_horizontal = ('groups', 'user_permissions')


class BedInline(admin.TabularInline):
    model = Bed
    extra = 0


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'capacity')
    search_fields = ('name',)
    inlines = [BedInline]


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ('label', 'room', 'status')
    list_filter = ('status', 'room')
    search_fields = ('label',)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('patient_id', 'name', 'age', 'admitting_doctor', 'created_at')
    search_fields = ('patient_id', 'name', 'admitting_doctor')
    readonly_fields = ('patient_id', 'created_at')


class AdditionalChargeInline(admin.TabularInline):
    model = AdditionalCharge
    extra = 0
    readonly_fields = ('recorded_by',)


class InvoiceInline(admin.TabularInline):
    model = Invoice
    extra = 0


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ('pk', 'patient', 'bed', 'admission_date', 'monthly_fee', 'status')
    list_filter = ('status',)
    search_fields = ('patient__name', 'patient__patient_id')
    inlines = [AdditionalChargeInline, InvoiceInline]


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ('recorded_by',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('pk', 'admission', 'billing_period_start', 'billing_period_end', 'total_due', 'status')
    list_filter = ('status',)
    inlines = [PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('pk', 'invoice', 'amount', 'paid_on', 'recorded_by')
    list_filter = ('paid_on',)


@admin.register(AdditionalCharge)
class AdditionalChargeAdmin(admin.ModelAdmin):
    list_display = ('pk', 'admission', 'category', 'amount', 'charge_date', 'recorded_by')
    list_filter = ('category', 'charge_date')


@admin.register(VitalReading)
class VitalReadingAdmin(admin.ModelAdmin):
    list_display = (
        'pk', 'admission', 'session', 'recorded_at',
        'bp_systolic', 'bp_diastolic', 'pulse', 'temperature', 'spo2', 'has_flag',
    )
    list_filter = ('session', 'has_flag')
    search_fields = ('admission__patient__name',)
    readonly_fields = ('recorded_by',)


@admin.register(VitalsThreshold)
class VitalsThresholdAdmin(admin.ModelAdmin):
    list_display = ('vital_type', 'below_threshold', 'above_threshold')
