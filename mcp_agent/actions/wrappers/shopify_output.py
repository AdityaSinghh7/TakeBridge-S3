import json

shopify_get_orders_with_filters_output_schema = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "orders": {
          "description": "Array of order objects. Returns up to 50 orders per request by default.",
          "items": {
            "description": "Shopify order object.",
            "properties": {
              "admin_graphql_api_id": {
                "description": "The admin GraphQL API ID for the order",
                "title": "Admin Graphql Api Id",
                "type": "string"
              },
              "app_id": {
                "default": None,
                "description": "The ID of the app that created the order",
                "nullable": True,
                "title": "App Id",
                "type": "integer"
              },
              "billing_address": {
                "additionalProperties": False,
                "default": None,
                "description": "Mailing address structure used for billing and shipping.",
                "nullable": True,
                "properties": {
                  "address1": {
                    "default": None,
                    "description": "Street address line 1",
                    "nullable": True,
                    "title": "Address1",
                    "type": "string"
                  },
                  "address2": {
                    "default": None,
                    "description": "Street address line 2",
                    "nullable": True,
                    "title": "Address2",
                    "type": "string"
                  },
                  "city": {
                    "default": None,
                    "description": "City, town, or village",
                    "nullable": True,
                    "title": "City",
                    "type": "string"
                  },
                  "company": {
                    "default": None,
                    "description": "Company name",
                    "nullable": True,
                    "title": "Company",
                    "type": "string"
                  },
                  "country": {
                    "default": None,
                    "description": "Country name",
                    "nullable": True,
                    "title": "Country",
                    "type": "string"
                  },
                  "country_code": {
                    "default": None,
                    "description": "Two-letter country code (ISO 3166-1 alpha-2)",
                    "nullable": True,
                    "title": "Country Code",
                    "type": "string"
                  },
                  "first_name": {
                    "default": None,
                    "description": "First name of the person",
                    "nullable": True,
                    "title": "First Name",
                    "type": "string"
                  },
                  "last_name": {
                    "default": None,
                    "description": "Last name of the person",
                    "nullable": True,
                    "title": "Last Name",
                    "type": "string"
                  },
                  "latitude": {
                    "default": None,
                    "description": "Geographic latitude coordinate",
                    "nullable": True,
                    "title": "Latitude",
                    "type": "number"
                  },
                  "longitude": {
                    "default": None,
                    "description": "Geographic longitude coordinate",
                    "nullable": True,
                    "title": "Longitude",
                    "type": "number"
                  },
                  "name": {
                    "default": None,
                    "description": "Full name",
                    "nullable": True,
                    "title": "Name",
                    "type": "string"
                  },
                  "phone": {
                    "default": None,
                    "description": "Phone number",
                    "nullable": True,
                    "title": "Phone",
                    "type": "string"
                  },
                  "province": {
                    "default": None,
                    "description": "Region, state, or prefecture",
                    "nullable": True,
                    "title": "Province",
                    "type": "string"
                  },
                  "province_code": {
                    "default": None,
                    "description": "Region code or abbreviation",
                    "nullable": True,
                    "title": "Province Code",
                    "type": "string"
                  },
                  "zip": {
                    "default": None,
                    "description": "Postal code",
                    "nullable": True,
                    "title": "Zip",
                    "type": "string"
                  }
                },
                "title": "Address",
                "type": "object"
              },
              "browser_ip": {
                "default": None,
                "description": "The IP address of the browser used by the customer when they placed the order",
                "nullable": True,
                "title": "Browser Ip",
                "type": "string"
              },
              "buyer_accepts_marketing": {
                "default": None,
                "description": "Whether the customer consented to receive email updates from the shop",
                "nullable": True,
                "title": "Buyer Accepts Marketing",
                "type": "boolean"
              },
              "cancel_reason": {
                "default": None,
                "description": "Reason for cancellation. Valid values: customer, fraud, inventory, declined, other",
                "nullable": True,
                "title": "Cancel Reason",
                "type": "string"
              },
              "cancelled_at": {
                "default": None,
                "description": "The date and time when the order was canceled (ISO 8601 format)",
                "nullable": True,
                "title": "Cancelled At",
                "type": "string"
              },
              "cart_token": {
                "default": None,
                "description": "Unique cart identifier (deprecated)",
                "nullable": True,
                "title": "Cart Token",
                "type": "string"
              },
              "checkout_id": {
                "default": None,
                "description": "Checkout identifier",
                "nullable": True,
                "title": "Checkout Id",
                "type": "integer"
              },
              "checkout_token": {
                "default": None,
                "description": "Unique checkout identifier (deprecated)",
                "nullable": True,
                "title": "Checkout Token",
                "type": "string"
              },
              "client_details": {
                "additionalProperties": False,
                "default": None,
                "description": "Browser and session information from when the order was placed.",
                "nullable": True,
                "properties": {
                  "accept_language": {
                    "default": None,
                    "description": "Browser language preferences",
                    "nullable": True,
                    "title": "Accept Language",
                    "type": "string"
                  },
                  "browser_height": {
                    "default": None,
                    "description": "Browser window height in pixels",
                    "nullable": True,
                    "title": "Browser Height",
                    "type": "integer"
                  },
                  "browser_ip": {
                    "default": None,
                    "description": "Browser IP address",
                    "nullable": True,
                    "title": "Browser Ip",
                    "type": "string"
                  },
                  "browser_width": {
                    "default": None,
                    "description": "Browser window width in pixels",
                    "nullable": True,
                    "title": "Browser Width",
                    "type": "integer"
                  },
                  "session_hash": {
                    "default": None,
                    "description": "Session identifier hash",
                    "nullable": True,
                    "title": "Session Hash",
                    "type": "string"
                  },
                  "user_agent": {
                    "default": None,
                    "description": "Browser and operating system details",
                    "nullable": True,
                    "title": "User Agent",
                    "type": "string"
                  }
                },
                "title": "ClientDetails",
                "type": "object"
              },
              "closed_at": {
                "default": None,
                "description": "The date and time when the order was closed (ISO 8601 format)",
                "nullable": True,
                "title": "Closed At",
                "type": "string"
              },
              "company": {
                "additionalProperties": True,
                "default": None,
                "description": "Represents information about the purchasing company for the order",
                "nullable": True,
                "title": "Company",
                "type": "object"
              },
              "confirmation_number": {
                "default": None,
                "description": "Randomly generated alpha-numeric identifier for the order that may be shown to the customer",
                "nullable": True,
                "title": "Confirmation Number",
                "type": "string"
              },
              "confirmed": {
                "default": None,
                "description": "Whether the order has been confirmed",
                "nullable": True,
                "title": "Confirmed",
                "type": "boolean"
              },
              "contact_email": {
                "default": None,
                "description": "Contact email address for the order",
                "nullable": True,
                "title": "Contact Email",
                "type": "string"
              },
              "created_at": {
                "description": "Order creation timestamp (ISO 8601 format)",
                "title": "Created At",
                "type": "string"
              },
              "currency": {
                "description": "Three-letter code (ISO 4217 format) for the shop currency",
                "title": "Currency",
                "type": "string"
              },
              "current_subtotal_price": {
                "default": None,
                "description": "Current subtotal price after adjustments and refunds",
                "nullable": True,
                "title": "Current Subtotal Price",
                "type": "string"
              },
              "current_subtotal_price_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "current_total_discounts": {
                "default": None,
                "description": "Current total discounts after adjustments",
                "nullable": True,
                "title": "Current Total Discounts",
                "type": "string"
              },
              "current_total_discounts_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "current_total_duties_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "current_total_price": {
                "default": None,
                "description": "Current total price of the order after adjustments and refunds in the shop currency",
                "nullable": True,
                "title": "Current Total Price",
                "type": "string"
              },
              "current_total_price_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "current_total_tax": {
                "default": None,
                "description": "Current total tax after adjustments",
                "nullable": True,
                "title": "Current Total Tax",
                "type": "string"
              },
              "current_total_tax_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "customer": {
                "additionalProperties": False,
                "default": None,
                "description": "Customer details object.",
                "nullable": True,
                "properties": {
                  "accepts_marketing": {
                    "default": None,
                    "description": "Whether customer accepts marketing",
                    "nullable": True,
                    "title": "Accepts Marketing",
                    "type": "boolean"
                  },
                  "accepts_marketing_updated_at": {
                    "default": None,
                    "description": "When marketing consent was updated",
                    "nullable": True,
                    "title": "Accepts Marketing Updated At",
                    "type": "string"
                  },
                  "admin_graphql_api_id": {
                    "default": None,
                    "description": "Admin GraphQL API ID for customer",
                    "nullable": True,
                    "title": "Admin Graphql Api Id",
                    "type": "string"
                  },
                  "created_at": {
                    "default": None,
                    "description": "Customer creation timestamp",
                    "nullable": True,
                    "title": "Created At",
                    "type": "string"
                  },
                  "currency": {
                    "default": None,
                    "description": "Customer's currency",
                    "nullable": True,
                    "title": "Currency",
                    "type": "string"
                  },
                  "default_address": {
                    "additionalProperties": True,
                    "default": None,
                    "description": "Customer's default address",
                    "nullable": True,
                    "title": "Default Address",
                    "type": "object"
                  },
                  "email": {
                    "default": None,
                    "description": "Customer email address",
                    "nullable": True,
                    "title": "Email",
                    "type": "string"
                  },
                  "email_marketing_consent": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Email marketing consent information.",
                    "nullable": True,
                    "properties": {
                      "consent_updated_at": {
                        "default": None,
                        "description": "When consent was updated",
                        "nullable": True,
                        "title": "Consent Updated At",
                        "type": "string"
                      },
                      "opt_in_level": {
                        "default": None,
                        "description": "Opt-in level",
                        "nullable": True,
                        "title": "Opt In Level",
                        "type": "string"
                      },
                      "state": {
                        "default": None,
                        "description": "Consent state",
                        "nullable": True,
                        "title": "State",
                        "type": "string"
                      }
                    },
                    "title": "EmailMarketingConsent",
                    "type": "object"
                  },
                  "first_name": {
                    "default": None,
                    "description": "Customer first name",
                    "nullable": True,
                    "title": "First Name",
                    "type": "string"
                  },
                  "id": {
                    "default": None,
                    "description": "Customer identifier",
                    "nullable": True,
                    "title": "Id",
                    "type": "integer"
                  },
                  "last_name": {
                    "default": None,
                    "description": "Customer last name",
                    "nullable": True,
                    "title": "Last Name",
                    "type": "string"
                  },
                  "last_order_id": {
                    "default": None,
                    "description": "ID of customer's last order",
                    "nullable": True,
                    "title": "Last Order Id",
                    "type": "integer"
                  },
                  "last_order_name": {
                    "default": None,
                    "description": "Name of customer's last order",
                    "nullable": True,
                    "title": "Last Order Name",
                    "type": "string"
                  },
                  "marketing_opt_in_level": {
                    "default": None,
                    "description": "Marketing opt-in level",
                    "nullable": True,
                    "title": "Marketing Opt In Level",
                    "type": "string"
                  },
                  "multipass_identifier": {
                    "default": None,
                    "description": "Multipass login identifier",
                    "nullable": True,
                    "title": "Multipass Identifier",
                    "type": "string"
                  },
                  "note": {
                    "default": None,
                    "description": "Note about the customer",
                    "nullable": True,
                    "title": "Note",
                    "type": "string"
                  },
                  "orders_count": {
                    "default": None,
                    "description": "Number of orders placed by customer",
                    "nullable": True,
                    "title": "Orders Count",
                    "type": "integer"
                  },
                  "phone": {
                    "default": None,
                    "description": "Customer phone number",
                    "nullable": True,
                    "title": "Phone",
                    "type": "string"
                  },
                  "sms_marketing_consent": {
                    "additionalProperties": True,
                    "default": None,
                    "description": "SMS marketing consent information",
                    "nullable": True,
                    "title": "Sms Marketing Consent",
                    "type": "object"
                  },
                  "state": {
                    "default": None,
                    "description": "Customer account state",
                    "nullable": True,
                    "title": "State",
                    "type": "string"
                  },
                  "tags": {
                    "default": None,
                    "description": "Customer tags",
                    "nullable": True,
                    "title": "Tags",
                    "type": "string"
                  },
                  "tax_exempt": {
                    "default": None,
                    "description": "Whether customer is tax exempt",
                    "nullable": True,
                    "title": "Tax Exempt",
                    "type": "boolean"
                  },
                  "tax_exemptions": {
                    "default": None,
                    "description": "List of tax exemptions",
                    "items": {
                      "properties": {},
                      "type": "string"
                    },
                    "nullable": True,
                    "title": "Tax Exemptions",
                    "type": "array"
                  },
                  "total_spent": {
                    "default": None,
                    "description": "Total amount spent by customer",
                    "nullable": True,
                    "title": "Total Spent",
                    "type": "string"
                  },
                  "updated_at": {
                    "default": None,
                    "description": "Customer last update timestamp",
                    "nullable": True,
                    "title": "Updated At",
                    "type": "string"
                  },
                  "verified_email": {
                    "default": None,
                    "description": "Whether email is verified",
                    "nullable": True,
                    "title": "Verified Email",
                    "type": "boolean"
                  }
                },
                "title": "Customer",
                "type": "object"
              },
              "customer_locale": {
                "default": None,
                "description": "Two-letter or three-letter language code",
                "nullable": True,
                "title": "Customer Locale",
                "type": "string"
              },
              "device_id": {
                "default": None,
                "description": "Device identifier",
                "nullable": True,
                "title": "Device Id",
                "type": "integer"
              },
              "discount_applications": {
                "default": None,
                "description": "Ordered list of discount applications",
                "items": {
                  "description": "Discount application details.",
                  "properties": {
                    "allocation_method": {
                      "default": None,
                      "description": "How discount is allocated",
                      "nullable": True,
                      "title": "Allocation Method",
                      "type": "string"
                    },
                    "description": {
                      "default": None,
                      "description": "Discount description",
                      "nullable": True,
                      "title": "Description",
                      "type": "string"
                    },
                    "target_selection": {
                      "default": None,
                      "description": "Target selection method",
                      "nullable": True,
                      "title": "Target Selection",
                      "type": "string"
                    },
                    "target_type": {
                      "default": None,
                      "description": "Target type (line_item, shipping_line)",
                      "nullable": True,
                      "title": "Target Type",
                      "type": "string"
                    },
                    "title": {
                      "default": None,
                      "description": "Discount title",
                      "nullable": True,
                      "title": "Title",
                      "type": "string"
                    },
                    "type": {
                      "default": None,
                      "description": "Discount application type",
                      "nullable": True,
                      "title": "Type",
                      "type": "string"
                    },
                    "value": {
                      "default": None,
                      "description": "Discount value",
                      "nullable": True,
                      "title": "Value",
                      "type": "string"
                    },
                    "value_type": {
                      "default": None,
                      "description": "Value type (fixed_amount, percentage)",
                      "nullable": True,
                      "title": "Value Type",
                      "type": "string"
                    }
                  },
                  "title": "DiscountApplication",
                  "type": "object"
                },
                "nullable": True,
                "title": "Discount Applications",
                "type": "array"
              },
              "discount_codes": {
                "default": None,
                "description": "Applied discount codes with amounts",
                "items": {
                  "description": "Applied discount code with amount.",
                  "properties": {
                    "amount": {
                      "default": None,
                      "description": "Discount percentage or monetary amount",
                      "nullable": True,
                      "title": "Amount",
                      "type": "string"
                    },
                    "code": {
                      "default": None,
                      "description": "Discount code or title",
                      "nullable": True,
                      "title": "Code",
                      "type": "string"
                    },
                    "type": {
                      "default": None,
                      "description": "Discount type (fixed_amount, percentage, shipping)",
                      "nullable": True,
                      "title": "Type",
                      "type": "string"
                    }
                  },
                  "title": "DiscountCode",
                  "type": "object"
                },
                "nullable": True,
                "title": "Discount Codes",
                "type": "array"
              },
              "email": {
                "default": None,
                "description": "Customer's email address",
                "nullable": True,
                "title": "Email",
                "type": "string"
              },
              "financial_status": {
                "default": None,
                "description": "Payment status. Valid values: pending, authorized, partially_paid, paid, partially_refunded, refunded, voided",
                "nullable": True,
                "title": "Financial Status",
                "type": "string"
              },
              "fulfillment_status": {
                "default": None,
                "description": "Order fulfillment status. Valid values: fulfilled, partial, null (unfulfilled), restocked",
                "nullable": True,
                "title": "Fulfillment Status",
                "type": "string"
              },
              "fulfillments": {
                "default": None,
                "description": "Array of fulfillments associated with the order",
                "items": {
                  "additionalProperties": True,
                  "properties": {},
                  "type": "object"
                },
                "nullable": True,
                "title": "Fulfillments",
                "type": "array"
              },
              "gateway": {
                "default": None,
                "description": "Payment gateway used for the order",
                "nullable": True,
                "title": "Gateway",
                "type": "string"
              },
              "id": {
                "description": "Unique order identifier",
                "title": "Id",
                "type": "integer"
              },
              "landing_site": {
                "default": None,
                "description": "The URL for the page where the buyer landed when they entered the shop",
                "nullable": True,
                "title": "Landing Site",
                "type": "string"
              },
              "landing_site_ref": {
                "default": None,
                "description": "The landing site referrer value",
                "nullable": True,
                "title": "Landing Site Ref",
                "type": "string"
              },
              "line_items": {
                "description": "List of line item objects, each containing information about an item in the order",
                "items": {
                  "description": "Line item object containing information about an item in the order.",
                  "properties": {
                    "admin_graphql_api_id": {
                      "default": None,
                      "description": "Admin GraphQL API ID",
                      "nullable": True,
                      "title": "Admin Graphql Api Id",
                      "type": "string"
                    },
                    "attributed_staffs": {
                      "default": None,
                      "description": "Staff attribution details",
                      "items": {
                        "additionalProperties": True,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": True,
                      "title": "Attributed Staffs",
                      "type": "array"
                    },
                    "current_quantity": {
                      "default": None,
                      "description": "Quantity minus removed amount",
                      "nullable": True,
                      "title": "Current Quantity",
                      "type": "integer"
                    },
                    "discount_allocations": {
                      "default": None,
                      "description": "Individual discount application details",
                      "items": {
                        "additionalProperties": True,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": True,
                      "title": "Discount Allocations",
                      "type": "array"
                    },
                    "duties": {
                      "default": None,
                      "description": "Duty information",
                      "items": {
                        "additionalProperties": True,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": True,
                      "title": "Duties",
                      "type": "array"
                    },
                    "fulfillable_quantity": {
                      "default": None,
                      "description": "Available to fulfill quantity",
                      "nullable": True,
                      "title": "Fulfillable Quantity",
                      "type": "integer"
                    },
                    "fulfillment_service": {
                      "default": None,
                      "description": "Service handling fulfillment",
                      "nullable": True,
                      "title": "Fulfillment Service",
                      "type": "string"
                    },
                    "fulfillment_status": {
                      "default": None,
                      "description": "Item fulfillment state",
                      "nullable": True,
                      "title": "Fulfillment Status",
                      "type": "string"
                    },
                    "gift_card": {
                      "default": None,
                      "description": "Whether item is a gift card",
                      "nullable": True,
                      "title": "Gift Card",
                      "type": "boolean"
                    },
                    "grams": {
                      "default": None,
                      "description": "Item weight in grams",
                      "nullable": True,
                      "title": "Grams",
                      "type": "integer"
                    },
                    "id": {
                      "description": "Line item identifier",
                      "title": "Id",
                      "type": "integer"
                    },
                    "name": {
                      "default": None,
                      "description": "Product variant name",
                      "nullable": True,
                      "title": "Name",
                      "type": "string"
                    },
                    "origin_location": {
                      "additionalProperties": True,
                      "default": None,
                      "description": "Fulfillment origin location",
                      "nullable": True,
                      "title": "Origin Location",
                      "type": "object"
                    },
                    "pre_tax_price": {
                      "default": None,
                      "description": "Price before tax",
                      "nullable": True,
                      "title": "Pre Tax Price",
                      "type": "string"
                    },
                    "pre_tax_price_set": {
                      "additionalProperties": False,
                      "default": None,
                      "description": "Price in shop and presentment currencies.",
                      "nullable": True,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "PriceSet",
                      "type": "object"
                    },
                    "price": {
                      "default": None,
                      "description": "Pre-discount item price",
                      "nullable": True,
                      "title": "Price",
                      "type": "string"
                    },
                    "price_set": {
                      "additionalProperties": False,
                      "default": None,
                      "description": "Price in shop and presentment currencies.",
                      "nullable": True,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "PriceSet",
                      "type": "object"
                    },
                    "product_exists": {
                      "default": None,
                      "description": "Whether product still exists",
                      "nullable": True,
                      "title": "Product Exists",
                      "type": "boolean"
                    },
                    "product_id": {
                      "default": None,
                      "description": "Product identifier",
                      "nullable": True,
                      "title": "Product Id",
                      "type": "integer"
                    },
                    "properties": {
                      "default": None,
                      "description": "Custom product options",
                      "items": {
                        "additionalProperties": True,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": True,
                      "title": "Properties",
                      "type": "array"
                    },
                    "quantity": {
                      "description": "Quantity purchased",
                      "title": "Quantity",
                      "type": "integer"
                    },
                    "requires_shipping": {
                      "default": None,
                      "description": "Shipping requirement flag",
                      "nullable": True,
                      "title": "Requires Shipping",
                      "type": "boolean"
                    },
                    "sku": {
                      "default": None,
                      "description": "Stock keeping unit",
                      "nullable": True,
                      "title": "Sku",
                      "type": "string"
                    },
                    "tax_lines": {
                      "default": None,
                      "description": "Applied taxes to item",
                      "items": {
                        "description": "Tax line applied to the order.",
                        "properties": {
                          "channel_liable": {
                            "default": None,
                            "description": "Whether the channel is liable for remitting the tax",
                            "nullable": True,
                            "title": "Channel Liable",
                            "type": "boolean"
                          },
                          "price": {
                            "default": None,
                            "description": "Tax amount in shop currency",
                            "nullable": True,
                            "title": "Price",
                            "type": "string"
                          },
                          "price_set": {
                            "additionalProperties": False,
                            "default": None,
                            "description": "Price in shop and presentment currencies.",
                            "nullable": True,
                            "properties": {
                              "presentment_money": {
                                "additionalProperties": False,
                                "default": None,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": True,
                                "properties": {
                                  "amount": {
                                    "default": None,
                                    "description": "Amount in decimal format",
                                    "nullable": True,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": None,
                                    "description": "Currency code (ISO 4217)",
                                    "nullable": True,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              },
                              "shop_money": {
                                "additionalProperties": False,
                                "default": None,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": True,
                                "properties": {
                                  "amount": {
                                    "default": None,
                                    "description": "Amount in decimal format",
                                    "nullable": True,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": None,
                                    "description": "Currency code (ISO 4217)",
                                    "nullable": True,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              }
                            },
                            "title": "PriceSet",
                            "type": "object"
                          },
                          "rate": {
                            "default": None,
                            "description": "Tax rate as decimal percentage",
                            "nullable": True,
                            "title": "Rate",
                            "type": "number"
                          },
                          "title": {
                            "default": None,
                            "description": "Tax name",
                            "nullable": True,
                            "title": "Title",
                            "type": "string"
                          }
                        },
                        "title": "TaxLine",
                        "type": "object"
                      },
                      "nullable": True,
                      "title": "Tax Lines",
                      "type": "array"
                    },
                    "taxable": {
                      "default": None,
                      "description": "Tax applicability flag",
                      "nullable": True,
                      "title": "Taxable",
                      "type": "boolean"
                    },
                    "tip_payment_gateway": {
                      "default": None,
                      "description": "Tip payment processor",
                      "nullable": True,
                      "title": "Tip Payment Gateway",
                      "type": "string"
                    },
                    "tip_payment_method": {
                      "default": None,
                      "description": "Tip payment type",
                      "nullable": True,
                      "title": "Tip Payment Method",
                      "type": "string"
                    },
                    "title": {
                      "default": None,
                      "description": "Product title",
                      "nullable": True,
                      "title": "Title",
                      "type": "string"
                    },
                    "total_discount": {
                      "default": None,
                      "description": "Allocated discount amount",
                      "nullable": True,
                      "title": "Total Discount",
                      "type": "string"
                    },
                    "total_discount_set": {
                      "additionalProperties": False,
                      "default": None,
                      "description": "Price in shop and presentment currencies.",
                      "nullable": True,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "PriceSet",
                      "type": "object"
                    },
                    "variant_id": {
                      "default": None,
                      "description": "Product variant identifier",
                      "nullable": True,
                      "title": "Variant Id",
                      "type": "integer"
                    },
                    "variant_inventory_management": {
                      "default": None,
                      "description": "Inventory management service",
                      "nullable": True,
                      "title": "Variant Inventory Management",
                      "type": "string"
                    },
                    "variant_title": {
                      "default": None,
                      "description": "Variant-specific title",
                      "nullable": True,
                      "title": "Variant Title",
                      "type": "string"
                    },
                    "vendor": {
                      "default": None,
                      "description": "Item supplier name",
                      "nullable": True,
                      "title": "Vendor",
                      "type": "string"
                    }
                  },
                  "required": [
                    "id",
                    "quantity"
                  ],
                  "title": "LineItem",
                  "type": "object"
                },
                "title": "Line Items",
                "type": "array"
              },
              "location_id": {
                "default": None,
                "description": "Location identifier where order was placed",
                "nullable": True,
                "title": "Location Id",
                "type": "integer"
              },
              "name": {
                "description": "Order name displayed to customer (e.g., '#1001')",
                "title": "Name",
                "type": "string"
              },
              "note": {
                "default": None,
                "description": "Additional information or instructions added to the order (e.g., gift message, delivery instructions)",
                "nullable": True,
                "title": "Note",
                "type": "string"
              },
              "note_attributes": {
                "default": None,
                "description": "List of additional information attached to the order as key-value pairs",
                "items": {
                  "additionalProperties": True,
                  "properties": {},
                  "type": "object"
                },
                "nullable": True,
                "title": "Note Attributes",
                "type": "array"
              },
              "number": {
                "description": "Sequential order number",
                "title": "Number",
                "type": "integer"
              },
              "order_number": {
                "description": "Sequential order number displayed to customers",
                "title": "Order Number",
                "type": "integer"
              },
              "order_status_url": {
                "default": None,
                "description": "URL for the order status page",
                "nullable": True,
                "title": "Order Status Url",
                "type": "string"
              },
              "original_total_duties_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "payment_gateway_names": {
                "default": None,
                "description": "Array of payment gateway names used for the order",
                "items": {
                  "properties": {},
                  "type": "string"
                },
                "nullable": True,
                "title": "Payment Gateway Names",
                "type": "array"
              },
              "payment_terms": {
                "additionalProperties": True,
                "default": None,
                "description": "Payment terms for the order",
                "nullable": True,
                "title": "Payment Terms",
                "type": "object"
              },
              "phone": {
                "default": None,
                "description": "Customer's phone number for SMS notifications",
                "nullable": True,
                "title": "Phone",
                "type": "string"
              },
              "presentment_currency": {
                "default": None,
                "description": "Currency code (ISO 4217) for the currency the customer used at checkout",
                "nullable": True,
                "title": "Presentment Currency",
                "type": "string"
              },
              "processed_at": {
                "default": None,
                "description": "Processing completion timestamp (ISO 8601 format)",
                "nullable": True,
                "title": "Processed At",
                "type": "string"
              },
              "processing_method": {
                "default": None,
                "description": "How the payment was processed",
                "nullable": True,
                "title": "Processing Method",
                "type": "string"
              },
              "reference": {
                "default": None,
                "description": "Reference identifier",
                "nullable": True,
                "title": "Reference",
                "type": "string"
              },
              "referring_site": {
                "default": None,
                "description": "The website that referred the customer to the shop",
                "nullable": True,
                "title": "Referring Site",
                "type": "string"
              },
              "refunds": {
                "default": None,
                "description": "Array of refund objects associated with the order",
                "items": {
                  "additionalProperties": True,
                  "properties": {},
                  "type": "object"
                },
                "nullable": True,
                "title": "Refunds",
                "type": "array"
              },
              "shipping_address": {
                "additionalProperties": False,
                "default": None,
                "description": "Mailing address structure used for billing and shipping.",
                "nullable": True,
                "properties": {
                  "address1": {
                    "default": None,
                    "description": "Street address line 1",
                    "nullable": True,
                    "title": "Address1",
                    "type": "string"
                  },
                  "address2": {
                    "default": None,
                    "description": "Street address line 2",
                    "nullable": True,
                    "title": "Address2",
                    "type": "string"
                  },
                  "city": {
                    "default": None,
                    "description": "City, town, or village",
                    "nullable": True,
                    "title": "City",
                    "type": "string"
                  },
                  "company": {
                    "default": None,
                    "description": "Company name",
                    "nullable": True,
                    "title": "Company",
                    "type": "string"
                  },
                  "country": {
                    "default": None,
                    "description": "Country name",
                    "nullable": True,
                    "title": "Country",
                    "type": "string"
                  },
                  "country_code": {
                    "default": None,
                    "description": "Two-letter country code (ISO 3166-1 alpha-2)",
                    "nullable": True,
                    "title": "Country Code",
                    "type": "string"
                  },
                  "first_name": {
                    "default": None,
                    "description": "First name of the person",
                    "nullable": True,
                    "title": "First Name",
                    "type": "string"
                  },
                  "last_name": {
                    "default": None,
                    "description": "Last name of the person",
                    "nullable": True,
                    "title": "Last Name",
                    "type": "string"
                  },
                  "latitude": {
                    "default": None,
                    "description": "Geographic latitude coordinate",
                    "nullable": True,
                    "title": "Latitude",
                    "type": "number"
                  },
                  "longitude": {
                    "default": None,
                    "description": "Geographic longitude coordinate",
                    "nullable": True,
                    "title": "Longitude",
                    "type": "number"
                  },
                  "name": {
                    "default": None,
                    "description": "Full name",
                    "nullable": True,
                    "title": "Name",
                    "type": "string"
                  },
                  "phone": {
                    "default": None,
                    "description": "Phone number",
                    "nullable": True,
                    "title": "Phone",
                    "type": "string"
                  },
                  "province": {
                    "default": None,
                    "description": "Region, state, or prefecture",
                    "nullable": True,
                    "title": "Province",
                    "type": "string"
                  },
                  "province_code": {
                    "default": None,
                    "description": "Region code or abbreviation",
                    "nullable": True,
                    "title": "Province Code",
                    "type": "string"
                  },
                  "zip": {
                    "default": None,
                    "description": "Postal code",
                    "nullable": True,
                    "title": "Zip",
                    "type": "string"
                  }
                },
                "title": "Address",
                "type": "object"
              },
              "shipping_lines": {
                "default": None,
                "description": "Array of shipping line objects",
                "items": {
                  "description": "Shipping line object.",
                  "properties": {
                    "carrier_identifier": {
                      "default": None,
                      "description": "Carrier identifier",
                      "nullable": True,
                      "title": "Carrier Identifier",
                      "type": "string"
                    },
                    "code": {
                      "default": None,
                      "description": "Shipping code",
                      "nullable": True,
                      "title": "Code",
                      "type": "string"
                    },
                    "delivery_category": {
                      "default": None,
                      "description": "Delivery category",
                      "nullable": True,
                      "title": "Delivery Category",
                      "type": "string"
                    },
                    "discount_allocations": {
                      "default": None,
                      "description": "Discount allocations for shipping",
                      "items": {
                        "additionalProperties": True,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": True,
                      "title": "Discount Allocations",
                      "type": "array"
                    },
                    "discounted_price": {
                      "default": None,
                      "description": "Shipping price after discounts",
                      "nullable": True,
                      "title": "Discounted Price",
                      "type": "string"
                    },
                    "discounted_price_set": {
                      "additionalProperties": False,
                      "default": None,
                      "description": "Price in shop and presentment currencies.",
                      "nullable": True,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "PriceSet",
                      "type": "object"
                    },
                    "id": {
                      "default": None,
                      "description": "Shipping line identifier",
                      "nullable": True,
                      "title": "Id",
                      "type": "integer"
                    },
                    "phone": {
                      "default": None,
                      "description": "Phone number",
                      "nullable": True,
                      "title": "Phone",
                      "type": "string"
                    },
                    "price": {
                      "default": None,
                      "description": "Shipping price",
                      "nullable": True,
                      "title": "Price",
                      "type": "string"
                    },
                    "price_set": {
                      "additionalProperties": False,
                      "default": None,
                      "description": "Price in shop and presentment currencies.",
                      "nullable": True,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "PriceSet",
                      "type": "object"
                    },
                    "requested_fulfillment_service_id": {
                      "default": None,
                      "description": "Requested fulfillment service ID",
                      "nullable": True,
                      "title": "Requested Fulfillment Service Id",
                      "type": "string"
                    },
                    "source": {
                      "default": None,
                      "description": "Shipping line source",
                      "nullable": True,
                      "title": "Source",
                      "type": "string"
                    },
                    "tax_lines": {
                      "default": None,
                      "description": "Tax lines for shipping",
                      "items": {
                        "description": "Tax line applied to the order.",
                        "properties": {
                          "channel_liable": {
                            "default": None,
                            "description": "Whether the channel is liable for remitting the tax",
                            "nullable": True,
                            "title": "Channel Liable",
                            "type": "boolean"
                          },
                          "price": {
                            "default": None,
                            "description": "Tax amount in shop currency",
                            "nullable": True,
                            "title": "Price",
                            "type": "string"
                          },
                          "price_set": {
                            "additionalProperties": False,
                            "default": None,
                            "description": "Price in shop and presentment currencies.",
                            "nullable": True,
                            "properties": {
                              "presentment_money": {
                                "additionalProperties": False,
                                "default": None,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": True,
                                "properties": {
                                  "amount": {
                                    "default": None,
                                    "description": "Amount in decimal format",
                                    "nullable": True,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": None,
                                    "description": "Currency code (ISO 4217)",
                                    "nullable": True,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              },
                              "shop_money": {
                                "additionalProperties": False,
                                "default": None,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": True,
                                "properties": {
                                  "amount": {
                                    "default": None,
                                    "description": "Amount in decimal format",
                                    "nullable": True,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": None,
                                    "description": "Currency code (ISO 4217)",
                                    "nullable": True,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              }
                            },
                            "title": "PriceSet",
                            "type": "object"
                          },
                          "rate": {
                            "default": None,
                            "description": "Tax rate as decimal percentage",
                            "nullable": True,
                            "title": "Rate",
                            "type": "number"
                          },
                          "title": {
                            "default": None,
                            "description": "Tax name",
                            "nullable": True,
                            "title": "Title",
                            "type": "string"
                          }
                        },
                        "title": "TaxLine",
                        "type": "object"
                      },
                      "nullable": True,
                      "title": "Tax Lines",
                      "type": "array"
                    },
                    "title": {
                      "default": None,
                      "description": "Shipping method title",
                      "nullable": True,
                      "title": "Title",
                      "type": "string"
                    }
                  },
                  "title": "ShippingLine",
                  "type": "object"
                },
                "nullable": True,
                "title": "Shipping Lines",
                "type": "array"
              },
              "source_identifier": {
                "default": None,
                "description": "Source identifier for the order",
                "nullable": True,
                "title": "Source Identifier",
                "type": "string"
              },
              "source_name": {
                "default": None,
                "description": "Source name where the order originated (e.g., 'web', 'pos', 'shopify_draft_order')",
                "nullable": True,
                "title": "Source Name",
                "type": "string"
              },
              "source_url": {
                "default": None,
                "description": "Source URL for the order",
                "nullable": True,
                "title": "Source Url",
                "type": "string"
              },
              "subtotal_price": {
                "default": None,
                "description": "Total price before shipping and taxes",
                "nullable": True,
                "title": "Subtotal Price",
                "type": "string"
              },
              "subtotal_price_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "tags": {
                "default": None,
                "description": "Tags on the order, returned in alphabetical order as comma-separated values",
                "nullable": True,
                "title": "Tags",
                "type": "string"
              },
              "tax_lines": {
                "default": None,
                "description": "Tax lines applied to the order",
                "items": {
                  "description": "Tax line applied to the order.",
                  "properties": {
                    "channel_liable": {
                      "default": None,
                      "description": "Whether the channel is liable for remitting the tax",
                      "nullable": True,
                      "title": "Channel Liable",
                      "type": "boolean"
                    },
                    "price": {
                      "default": None,
                      "description": "Tax amount in shop currency",
                      "nullable": True,
                      "title": "Price",
                      "type": "string"
                    },
                    "price_set": {
                      "additionalProperties": False,
                      "default": None,
                      "description": "Price in shop and presentment currencies.",
                      "nullable": True,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": False,
                          "default": None,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": True,
                          "properties": {
                            "amount": {
                              "default": None,
                              "description": "Amount in decimal format",
                              "nullable": True,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": None,
                              "description": "Currency code (ISO 4217)",
                              "nullable": True,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "PriceSet",
                      "type": "object"
                    },
                    "rate": {
                      "default": None,
                      "description": "Tax rate as decimal percentage",
                      "nullable": True,
                      "title": "Rate",
                      "type": "number"
                    },
                    "title": {
                      "default": None,
                      "description": "Tax name",
                      "nullable": True,
                      "title": "Title",
                      "type": "string"
                    }
                  },
                  "title": "TaxLine",
                  "type": "object"
                },
                "nullable": True,
                "title": "Tax Lines",
                "type": "array"
              },
              "taxes_included": {
                "default": None,
                "description": "Whether taxes are included in the order prices",
                "nullable": True,
                "title": "Taxes Included",
                "type": "boolean"
              },
              "test": {
                "default": None,
                "description": "Whether this is a test order",
                "nullable": True,
                "title": "Test",
                "type": "boolean"
              },
              "token": {
                "default": None,
                "description": "Unique token for the order",
                "nullable": True,
                "title": "Token",
                "type": "string"
              },
              "total_discounts": {
                "default": None,
                "description": "Total discount amount applied to the order",
                "nullable": True,
                "title": "Total Discounts",
                "type": "string"
              },
              "total_discounts_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "total_line_items_price": {
                "default": None,
                "description": "Sum of the prices of all line items in the order, after any line item discounts have been applied",
                "nullable": True,
                "title": "Total Line Items Price",
                "type": "string"
              },
              "total_line_items_price_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "total_outstanding": {
                "default": None,
                "description": "Remaining amount due on the order",
                "nullable": True,
                "title": "Total Outstanding",
                "type": "string"
              },
              "total_price": {
                "description": "Total order price including taxes and discounts",
                "title": "Total Price",
                "type": "string"
              },
              "total_price_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "total_price_usd": {
                "default": None,
                "description": "Total price converted to USD",
                "nullable": True,
                "title": "Total Price Usd",
                "type": "string"
              },
              "total_shipping_price_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "total_tax": {
                "default": None,
                "description": "Sum of the prices for all tax lines applied to the order",
                "nullable": True,
                "title": "Total Tax",
                "type": "string"
              },
              "total_tax_set": {
                "additionalProperties": False,
                "default": None,
                "description": "Price in shop and presentment currencies.",
                "nullable": True,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": True,
                    "properties": {
                      "amount": {
                        "default": None,
                        "description": "Amount in decimal format",
                        "nullable": True,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": None,
                        "description": "Currency code (ISO 4217)",
                        "nullable": True,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "PriceSet",
                "type": "object"
              },
              "total_tip_received": {
                "default": None,
                "description": "Total tip amount received for the order",
                "nullable": True,
                "title": "Total Tip Received",
                "type": "string"
              },
              "total_weight": {
                "default": None,
                "description": "Total weight of the order after returns and refunds, in grams",
                "nullable": True,
                "title": "Total Weight",
                "type": "integer"
              },
              "updated_at": {
                "description": "Last update timestamp (ISO 8601 format)",
                "title": "Updated At",
                "type": "string"
              },
              "user_id": {
                "default": None,
                "description": "User identifier associated with the order",
                "nullable": True,
                "title": "User Id",
                "type": "integer"
              }
            },
            "required": [
              "id",
              "admin_graphql_api_id",
              "created_at",
              "currency",
              "line_items",
              "name",
              "number",
              "order_number",
              "total_price",
              "updated_at"
            ],
            "title": "Order",
            "type": "object"
          },
          "title": "Orders",
          "type": "array"
        }
      },
      "required": [
        "orders"
      ],
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "GetOrdersWithFiltersResponseWrapper",
  "type": "object"
}









































SHOPIFY_UPDATE_ORDER_OUTPUT_SCHEMA = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "admin_graphql_api_id": {
          "description": "GraphQL-compatible resource identifier",
          "title": "Admin Graphql Api Id",
          "type": "string"
        },
        "app_id": {
          "default": None,
          "description": "ID of app that created the order",
          "nullable": True,
          "title": "App Id",
          "type": "integer"
        },
        "billing_address": {
          "additionalProperties": False,
          "default": None,
          "description": "The mailing address associated with the payment method",
          "nullable": True,
          "properties": {
            "address1": {
              "default": None,
              "description": "The street address",
              "nullable": True,
              "title": "Address1",
              "type": "string"
            },
            "address2": {
              "default": None,
              "description": "An optional additional field for the street address",
              "nullable": True,
              "title": "Address2",
              "type": "string"
            },
            "city": {
              "default": None,
              "description": "The city, town, or village",
              "nullable": True,
              "title": "City",
              "type": "string"
            },
            "company": {
              "default": None,
              "description": "The company of the person",
              "nullable": True,
              "title": "Company",
              "type": "string"
            },
            "country": {
              "default": None,
              "description": "The name of the country",
              "nullable": True,
              "title": "Country",
              "type": "string"
            },
            "country_code": {
              "default": None,
              "description": "Two-letter code (ISO 3166-1 format)",
              "nullable": True,
              "title": "Country Code",
              "type": "string"
            },
            "first_name": {
              "default": None,
              "description": "Person's first name",
              "nullable": True,
              "title": "First Name",
              "type": "string"
            },
            "last_name": {
              "default": None,
              "description": "Person's last name",
              "nullable": True,
              "title": "Last Name",
              "type": "string"
            },
            "latitude": {
              "default": None,
              "description": "Geographic latitude coordinate",
              "nullable": True,
              "title": "Latitude",
              "type": "string"
            },
            "longitude": {
              "default": None,
              "description": "Geographic longitude coordinate",
              "nullable": True,
              "title": "Longitude",
              "type": "string"
            },
            "name": {
              "default": None,
              "description": "The full name of the person",
              "nullable": True,
              "title": "Name",
              "type": "string"
            },
            "phone": {
              "default": None,
              "description": "Phone number at address",
              "nullable": True,
              "title": "Phone",
              "type": "string"
            },
            "province": {
              "default": None,
              "description": "The name of the region (province, state, prefecture)",
              "nullable": True,
              "title": "Province",
              "type": "string"
            },
            "province_code": {
              "default": None,
              "description": "Alphanumeric abbreviation of the region",
              "nullable": True,
              "title": "Province Code",
              "type": "string"
            },
            "zip": {
              "default": None,
              "description": "Postal code (zip, postcode, or Eircode)",
              "nullable": True,
              "title": "Zip",
              "type": "string"
            }
          },
          "title": "Address",
          "type": "object"
        },
        "browser_ip": {
          "default": None,
          "description": "IP address of browser used at checkout",
          "nullable": True,
          "title": "Browser Ip",
          "type": "string"
        },
        "buyer_accepts_marketing": {
          "description": "Whether customer consented to email updates",
          "title": "Buyer Accepts Marketing",
          "type": "boolean"
        },
        "cancel_reason": {
          "default": None,
          "description": "Reason for cancellation (customer, fraud, inventory, declined, other)",
          "nullable": True,
          "title": "Cancel Reason",
          "type": "string"
        },
        "cancelled_at": {
          "default": None,
          "description": "Timestamp when order was canceled (ISO 8601 format)",
          "nullable": True,
          "title": "Cancelled At",
          "type": "string"
        },
        "cart_token": {
          "default": None,
          "description": "Deprecated cart reference",
          "nullable": True,
          "title": "Cart Token",
          "type": "string"
        },
        "checkout_id": {
          "default": None,
          "description": "Associated checkout identifier",
          "nullable": True,
          "title": "Checkout Id",
          "type": "integer"
        },
        "checkout_token": {
          "default": None,
          "description": "Deprecated checkout reference",
          "nullable": True,
          "title": "Checkout Token",
          "type": "string"
        },
        "client_details": {
          "additionalProperties": False,
          "default": None,
          "description": "Browser information including user_agent, session_hash",
          "nullable": True,
          "properties": {
            "accept_language": {
              "default": None,
              "description": "The languages and locales that the browser understands",
              "nullable": True,
              "title": "Accept Language",
              "type": "string"
            },
            "browser_height": {
              "default": None,
              "description": "Browser screen height in pixels, if available",
              "nullable": True,
              "title": "Browser Height",
              "type": "integer"
            },
            "browser_ip": {
              "default": None,
              "description": "Browser IP address",
              "nullable": True,
              "title": "Browser Ip",
              "type": "string"
            },
            "browser_width": {
              "default": None,
              "description": "Browser screen width in pixels, if available",
              "nullable": True,
              "title": "Browser Width",
              "type": "integer"
            },
            "session_hash": {
              "default": None,
              "description": "A hash of the session",
              "nullable": True,
              "title": "Session Hash",
              "type": "string"
            },
            "user_agent": {
              "default": None,
              "description": "Details of the browsing client, including software and OS versions",
              "nullable": True,
              "title": "User Agent",
              "type": "string"
            }
          },
          "title": "ClientDetails",
          "type": "object"
        },
        "closed_at": {
          "default": None,
          "description": "When order was closed (ISO 8601 format)",
          "nullable": True,
          "title": "Closed At",
          "type": "string"
        },
        "company": {
          "additionalProperties": True,
          "default": None,
          "description": "Purchasing company info; null if none",
          "nullable": True,
          "title": "Company",
          "type": "object"
        },
        "confirmation_number": {
          "default": None,
          "description": "A randomly generated alpha-numeric identifier for the order",
          "nullable": True,
          "title": "Confirmation Number",
          "type": "string"
        },
        "confirmed": {
          "description": "Whether order confirmation was sent",
          "title": "Confirmed",
          "type": "boolean"
        },
        "contact_email": {
          "default": None,
          "description": "Email for order notifications",
          "nullable": True,
          "title": "Contact Email",
          "type": "string"
        },
        "created_at": {
          "description": "Timestamp when order was created (ISO 8601 format)",
          "title": "Created At",
          "type": "string"
        },
        "currency": {
          "description": "Three-letter shop currency code (ISO 4217 format)",
          "title": "Currency",
          "type": "string"
        },
        "current_subtotal_price": {
          "default": None,
          "description": "Line items subtotal in shop currency (current value after refunds)",
          "nullable": True,
          "title": "Current Subtotal Price",
          "type": "string"
        },
        "current_subtotal_price_set": {
          "additionalProperties": False,
          "default": None,
          "description": "Current subtotal in shop and presentment currencies",
          "nullable": True,
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "PriceSet",
          "type": "object"
        },
        "current_total_discounts": {
          "default": None,
          "description": "Total discount amount applied (current value)",
          "nullable": True,
          "title": "Current Total Discounts",
          "type": "string"
        },
        "current_total_discounts_set": {
          "additionalProperties": False,
          "default": None,
          "description": "Current discounts in dual currencies",
          "nullable": True,
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "PriceSet",
          "type": "object"
        },
        "current_total_duties_set": {
          "additionalProperties": False,
          "default": None,
          "description": "Updated duty amounts in shop and presentment currencies",
          "nullable": True,
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "PriceSet",
          "type": "object"
        },
        "current_total_price": {
          "default": None,
          "description": "Final order amount (current value after refunds)",
          "nullable": True,
          "title": "Current Total Price",
          "type": "string"
        },
        "current_total_price_set": {
          "additionalProperties": False,
          "default": None,
          "description": "Current final amount in dual currencies",
          "nullable": True,
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "PriceSet",
          "type": "object"
        },
        "current_total_tax": {
          "default": None,
          "description": "Tax sum after changes",
          "nullable": True,
          "title": "Current Total Tax",
          "type": "string"
        },
        "current_total_tax_set": {
          "additionalProperties": False,
          "default": None,
          "description": "Current taxes in dual currencies",
          "nullable": True,
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "PriceSet",
          "type": "object"
        },
        "customer": {
          "additionalProperties": False,
          "default": None,
          "description": "Customer information; may be null",
          "nullable": True,
          "properties": {
            "accepts_marketing": {
              "description": "Marketing preference",
              "title": "Accepts Marketing",
              "type": "boolean"
            },
            "accepts_marketing_updated_at": {
              "default": None,
              "description": "Marketing preference modification (ISO 8601 format)",
              "nullable": True,
              "title": "Accepts Marketing Updated At",
              "type": "string"
            },
            "admin_graphql_api_id": {
              "description": "GraphQL identifier",
              "title": "Admin Graphql Api Id",
              "type": "string"
            },
            "created_at": {
              "description": "Account creation date (ISO 8601 format)",
              "title": "Created At",
              "type": "string"
            },
            "currency": {
              "description": "Preferred currency code (ISO 4217 format)",
              "title": "Currency",
              "type": "string"
            },
            "default_address": {
              "additionalProperties": True,
              "default": None,
              "description": "Primary address information",
              "nullable": True,
              "title": "Default Address",
              "type": "object"
            },
            "email": {
              "default": None,
              "description": "Email address",
              "nullable": True,
              "title": "Email",
              "type": "string"
            },
            "email_marketing_consent": {
              "additionalProperties": True,
              "default": None,
              "description": "Email consent details",
              "nullable": True,
              "title": "Email Marketing Consent",
              "type": "object"
            },
            "first_name": {
              "default": None,
              "description": "Given name",
              "nullable": True,
              "title": "First Name",
              "type": "string"
            },
            "id": {
              "description": "Unique identifier",
              "title": "Id",
              "type": "integer"
            },
            "last_name": {
              "default": None,
              "description": "Family name",
              "nullable": True,
              "title": "Last Name",
              "type": "string"
            },
            "last_order_id": {
              "default": None,
              "description": "Most recent order identifier",
              "nullable": True,
              "title": "Last Order Id",
              "type": "integer"
            },
            "last_order_name": {
              "default": None,
              "description": "Recent order reference",
              "nullable": True,
              "title": "Last Order Name",
              "type": "string"
            },
            "marketing_opt_in_level": {
              "default": None,
              "description": "Consent level",
              "nullable": True,
              "title": "Marketing Opt In Level",
              "type": "string"
            },
            "multipass_identifier": {
              "default": None,
              "description": "Legacy identifier",
              "nullable": True,
              "title": "Multipass Identifier",
              "type": "string"
            },
            "note": {
              "default": None,
              "description": "Admin notes",
              "nullable": True,
              "title": "Note",
              "type": "string"
            },
            "orders_count": {
              "description": "Total purchase count",
              "title": "Orders Count",
              "type": "integer"
            },
            "phone": {
              "default": None,
              "description": "Contact number",
              "nullable": True,
              "title": "Phone",
              "type": "string"
            },
            "sms_marketing_consent": {
              "additionalProperties": True,
              "default": None,
              "description": "SMS consent details",
              "nullable": True,
              "title": "Sms Marketing Consent",
              "type": "object"
            },
            "state": {
              "description": "Account status (enabled or disabled)",
              "title": "State",
              "type": "string"
            },
            "tags": {
              "default": None,
              "description": "Comma-separated labels",
              "nullable": True,
              "title": "Tags",
              "type": "string"
            },
            "tax_exempt": {
              "description": "Tax obligation status",
              "title": "Tax Exempt",
              "type": "boolean"
            },
            "tax_exemptions": {
              "description": "Applicable tax exemptions",
              "items": {
                "properties": {}
              },
              "title": "Tax Exemptions",
              "type": "array"
            },
            "total_spent": {
              "description": "Lifetime purchase value",
              "title": "Total Spent",
              "type": "string"
            },
            "updated_at": {
              "description": "Last update timestamp (ISO 8601 format)",
              "title": "Updated At",
              "type": "string"
            },
            "verified_email": {
              "description": "Email verification status",
              "title": "Verified Email",
              "type": "boolean"
            }
          },
          "required": [
            "id",
            "accepts_marketing",
            "created_at",
            "updated_at",
            "orders_count",
            "state",
            "total_spent",
            "verified_email",
            "tax_exempt",
            "currency",
            "tax_exemptions",
            "admin_graphql_api_id"
          ],
          "title": "Customer",
          "type": "object"
        },
        "customer_locale": {
          "default": None,
          "description": "Customer's language preference",
          "nullable": True,
          "title": "Customer Locale",
          "type": "string"
        },
        "device_id": {
          "default": None,
          "description": "Device identifier",
          "nullable": True,
          "title": "Device Id",
          "type": "string"
        },
        "discount_applications": {
          "description": "Discount application details",
          "items": {
            "properties": {
              "allocation_method": {
                "description": "Application scope",
                "title": "Allocation Method",
                "type": "string"
              },
              "code": {
                "default": None,
                "description": "Promo/discount code",
                "nullable": True,
                "title": "Code",
                "type": "string"
              },
              "description": {
                "default": None,
                "description": "Human-readable explanation",
                "nullable": True,
                "title": "Description",
                "type": "string"
              },
              "target_selection": {
                "description": "Target selection (all, entitled, or explicit)",
                "title": "Target Selection",
                "type": "string"
              },
              "target_type": {
                "description": "Target type (line_item or shipping_line)",
                "title": "Target Type",
                "type": "string"
              },
              "title": {
                "default": None,
                "description": "Discount name",
                "nullable": True,
                "title": "Title",
                "type": "string"
              },
              "type": {
                "description": "Type (percentage, fixed_amount, or shipping)",
                "title": "Type",
                "type": "string"
              },
              "value": {
                "description": "Discount magnitude",
                "title": "Value",
                "type": "string"
              },
              "value_type": {
                "description": "Value type (percentage or fixed_amount)",
                "title": "Value Type",
                "type": "string"
              }
            },
            "required": [
              "type",
              "value",
              "value_type",
              "allocation_method",
              "target_selection",
              "target_type"
            ],
            "title": "DiscountApplication",
            "type": "object"
          },
          "title": "Discount Applications",
          "type": "array"
        },
        "discount_codes": {
          "description": "Applied discount codes with amounts and types",
          "items": {
            "properties": {}
          },
          "title": "Discount Codes",
          "type": "array"
        },
        "email": {
          "default": None,
          "description": "The customer's email address",
          "nullable": True,
          "title": "Email",
          "type": "string"
        },
        "estimated_taxes": {
          "default": None,
          "description": "Boolean indicating tax calculation status",
          "nullable": True,
          "title": "Estimated Taxes",
          "type": "boolean"
        },
        "financial_status": {
          "description": "Payment status (pending, authorized, paid, partially_paid, refunded, voided, partially_refunded, unpaid)",
          "title": "Financial Status",
          "type": "string"
        },
        "fulfillment_status": {
          "default": None,
          "description": "Fulfillment state (fulfilled, partial, null, restocked)",
          "nullable": True,
          "title": "Fulfillment Status",
          "type": "string"
        },
        "fulfillments": {
          "description": "Associated fulfillment records",
          "items": {
            "properties": {
              "admin_graphql_api_id": {
                "description": "GraphQL identifier",
                "title": "Admin Graphql Api Id",
                "type": "string"
              },
              "created_at": {
                "description": "Creation timestamp (ISO 8601 format)",
                "title": "Created At",
                "type": "string"
              },
              "id": {
                "description": "Unique identifier",
                "title": "Id",
                "type": "integer"
              },
              "line_items": {
                "description": "Items in this fulfillment",
                "items": {
                  "properties": {}
                },
                "title": "Line Items",
                "type": "array"
              },
              "location_id": {
                "default": None,
                "description": "Warehouse/location identifier",
                "nullable": True,
                "title": "Location Id",
                "type": "integer"
              },
              "name": {
                "default": None,
                "description": "Fulfillment reference name",
                "nullable": True,
                "title": "Name",
                "type": "string"
              },
              "order_id": {
                "description": "Associated order ID",
                "title": "Order Id",
                "type": "integer"
              },
              "origin_address": {
                "additionalProperties": True,
                "default": None,
                "description": "Fulfillment origin location details",
                "nullable": True,
                "title": "Origin Address",
                "type": "object"
              },
              "receipt": {
                "additionalProperties": True,
                "default": None,
                "description": "Shipping receipt information",
                "nullable": True,
                "title": "Receipt",
                "type": "object"
              },
              "service": {
                "additionalProperties": True,
                "default": None,
                "description": "Fulfillment service details",
                "nullable": True,
                "title": "Service",
                "type": "object"
              },
              "shipment_status": {
                "default": None,
                "description": "Current shipment status",
                "nullable": True,
                "title": "Shipment Status",
                "type": "string"
              },
              "status": {
                "description": "Status (pending, open, in_transit, out_for_delivery, attempted_delivery, canceled, failure, success)",
                "title": "Status",
                "type": "string"
              },
              "tracking_company": {
                "default": None,
                "description": "Carrier name",
                "nullable": True,
                "title": "Tracking Company",
                "type": "string"
              },
              "tracking_number": {
                "default": None,
                "description": "Primary tracking identifier",
                "nullable": True,
                "title": "Tracking Number",
                "type": "string"
              },
              "tracking_numbers": {
                "description": "All associated tracking numbers",
                "items": {
                  "properties": {}
                },
                "title": "Tracking Numbers",
                "type": "array"
              },
              "tracking_url": {
                "default": None,
                "description": "Carrier tracking link",
                "nullable": True,
                "title": "Tracking Url",
                "type": "string"
              },
              "tracking_urls": {
                "description": "Multiple tracking URLs",
                "items": {
                  "properties": {}
                },
                "title": "Tracking Urls",
                "type": "array"
              },
              "updated_at": {
                "description": "Last modification timestamp (ISO 8601 format)",
                "title": "Updated At",
                "type": "string"
              }
            },
            "required": [
              "id",
              "order_id",
              "status",
              "created_at",
              "updated_at",
              "line_items",
              "tracking_numbers",
              "tracking_urls",
              "admin_graphql_api_id"
            ],
            "title": "Fulfillment",
            "type": "object"
          },
          "title": "Fulfillments",
          "type": "array"
        },
        "gateway": {
          "default": None,
          "description": "Payment gateway used",
          "nullable": True,
          "title": "Gateway",
          "type": "string"
        },
        "id": {
          "description": "Unique identifier for the order",
          "title": "Id",
          "type": "integer"
        },
        "landing_site": {
          "default": None,
          "description": "Page where customer entered store",
          "nullable": True,
          "title": "Landing Site",
          "type": "string"
        },
        "landing_site_ref": {
          "default": None,
          "description": "Referrer query parameter",
          "nullable": True,
          "title": "Landing Site Ref",
          "type": "string"
        },
        "line_items": {
          "description": "Products in order with quantities, prices, fulfillment status",
          "items": {
            "properties": {
              "attributed_staffs": {
                "default": None,
                "description": "Staff members attributed with id and quantity",
                "items": {
                  "properties": {}
                },
                "nullable": True,
                "title": "Attributed Staffs",
                "type": "array"
              },
              "current_quantity": {
                "default": None,
                "description": "The line item's quantity, minus the removed quantity",
                "nullable": True,
                "title": "Current Quantity",
                "type": "integer"
              },
              "discount_allocations": {
                "description": "Ordered list of discount amounts per application",
                "items": {
                  "properties": {
                    "amount": {
                      "description": "Discount amount allocated to the line in shop currency",
                      "title": "Amount",
                      "type": "string"
                    },
                    "amount_set": {
                      "additionalProperties": False,
                      "description": "Amount in shop and presentment currencies",
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": False,
                          "description": "Amount in the customer's local currency",
                          "properties": {
                            "amount": {
                              "description": "Monetary amount",
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "description": "Currency code (ISO 4217 format)",
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "required": [
                            "amount",
                            "currency_code"
                          ],
                          "title": "Presentment Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": False,
                          "description": "Amount in the store's base currency",
                          "properties": {
                            "amount": {
                              "description": "Monetary amount",
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "description": "Currency code (ISO 4217 format)",
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "required": [
                            "amount",
                            "currency_code"
                          ],
                          "title": "Shop Money",
                          "type": "object"
                        }
                      },
                      "required": [
                        "shop_money",
                        "presentment_money"
                      ],
                      "title": "Amount Set",
                      "type": "object"
                    },
                    "discount_application_index": {
                      "description": "Index of the associated discount application in order's list",
                      "title": "Discount Application Index",
                      "type": "integer"
                    }
                  },
                  "required": [
                    "amount",
                    "amount_set",
                    "discount_application_index"
                  ],
                  "title": "DiscountAllocation",
                  "type": "object"
                },
                "title": "Discount Allocations",
                "type": "array"
              },
              "duties": {
                "description": "Duty objects for the line item",
                "items": {
                  "properties": {}
                },
                "title": "Duties",
                "type": "array"
              },
              "fulfillable_quantity": {
                "description": "Amount available to fulfill, calculated as: quantity - max(refunded_quantity, fulfilled_quantity)",
                "title": "Fulfillable Quantity",
                "type": "integer"
              },
              "fulfillment_service": {
                "default": None,
                "description": "Handle of a fulfillment service that stocks the product variant",
                "nullable": True,
                "title": "Fulfillment Service",
                "type": "string"
              },
              "fulfillment_status": {
                "default": None,
                "description": "Values: None, fulfilled, partial, not_eligible",
                "nullable": True,
                "title": "Fulfillment Status",
                "type": "string"
              },
              "gift_card": {
                "description": "If true, then the item is not taxed or considered for shipping",
                "title": "Gift Card",
                "type": "boolean"
              },
              "grams": {
                "description": "The weight of the item in grams",
                "title": "Grams",
                "type": "integer"
              },
              "id": {
                "description": "The ID of the line item",
                "title": "Id",
                "type": "string"
              },
              "name": {
                "description": "The name of the product variant",
                "title": "Name",
                "type": "string"
              },
              "origin_location": {
                "additionalProperties": False,
                "default": None,
                "description": "Fulfillment origin location details",
                "nullable": True,
                "properties": {
                  "address1": {
                    "default": None,
                    "description": "Street address of the item's supplier",
                    "nullable": True,
                    "title": "Address1",
                    "type": "string"
                  },
                  "address2": {
                    "default": None,
                    "description": "Suite number of the item's supplier",
                    "nullable": True,
                    "title": "Address2",
                    "type": "string"
                  },
                  "city": {
                    "default": None,
                    "description": "City of the item's supplier",
                    "nullable": True,
                    "title": "City",
                    "type": "string"
                  },
                  "country_code": {
                    "default": None,
                    "description": "ISO 3166-1 format country code",
                    "nullable": True,
                    "title": "Country Code",
                    "type": "string"
                  },
                  "id": {
                    "default": None,
                    "description": "Location ID of the line item's fulfillment origin",
                    "nullable": True,
                    "title": "Id",
                    "type": "integer"
                  },
                  "name": {
                    "default": None,
                    "description": "Name of the item's supplier",
                    "nullable": True,
                    "title": "Name",
                    "type": "string"
                  },
                  "province_code": {
                    "default": None,
                    "description": "Alphanumeric abbreviation for region",
                    "nullable": True,
                    "title": "Province Code",
                    "type": "string"
                  },
                  "zip": {
                    "default": None,
                    "description": "Zip of the item's supplier",
                    "nullable": True,
                    "title": "Zip",
                    "type": "string"
                  }
                },
                "title": "OriginLocation",
                "type": "object"
              },
              "price": {
                "description": "The price of the item before discounts have been applied",
                "title": "Price",
                "type": "string"
              },
              "price_set": {
                "additionalProperties": False,
                "description": "Price in shop and presentment currencies",
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "description": "Amount in the customer's local currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Presentment Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "description": "Amount in the store's base currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Shop Money",
                    "type": "object"
                  }
                },
                "required": [
                  "shop_money",
                  "presentment_money"
                ],
                "title": "Price Set",
                "type": "object"
              },
              "product_id": {
                "default": None,
                "description": "Can be null if the original product associated with the order is deleted",
                "nullable": True,
                "title": "Product Id",
                "type": "integer"
              },
              "properties": {
                "description": "Custom information for the item that has been added to the cart",
                "items": {
                  "properties": {}
                },
                "title": "Properties",
                "type": "array"
              },
              "quantity": {
                "description": "The number of items that were purchased",
                "title": "Quantity",
                "type": "integer"
              },
              "requires_shipping": {
                "description": "Shipping requirement indicator",
                "title": "Requires Shipping",
                "type": "boolean"
              },
              "sku": {
                "default": None,
                "description": "The item's SKU (stock keeping unit)",
                "nullable": True,
                "title": "Sku",
                "type": "string"
              },
              "tax_lines": {
                "description": "Tax details for the line item",
                "items": {
                  "properties": {}
                },
                "title": "Tax Lines",
                "type": "array"
              },
              "taxable": {
                "description": "Tax applicability flag",
                "title": "Taxable",
                "type": "boolean"
              },
              "title": {
                "description": "The title of the product",
                "title": "Title",
                "type": "string"
              },
              "total_discount": {
                "description": "Total amount of the discount allocated to the line item",
                "title": "Total Discount",
                "type": "string"
              },
              "total_discount_set": {
                "additionalProperties": False,
                "description": "Discount amount in both currencies",
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "description": "Amount in the customer's local currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Presentment Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "description": "Amount in the store's base currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Shop Money",
                    "type": "object"
                  }
                },
                "required": [
                  "shop_money",
                  "presentment_money"
                ],
                "title": "Total Discount Set",
                "type": "object"
              },
              "variant_id": {
                "default": None,
                "description": "Product variant identifier",
                "nullable": True,
                "title": "Variant Id",
                "type": "integer"
              },
              "variant_title": {
                "default": None,
                "description": "The title of the product variant",
                "nullable": True,
                "title": "Variant Title",
                "type": "string"
              },
              "vendor": {
                "default": None,
                "description": "The name of the item's supplier",
                "nullable": True,
                "title": "Vendor",
                "type": "string"
              }
            },
            "required": [
              "id",
              "title",
              "name",
              "quantity",
              "price",
              "price_set",
              "requires_shipping",
              "taxable",
              "gift_card",
              "grams",
              "fulfillable_quantity",
              "properties",
              "total_discount",
              "total_discount_set",
              "discount_allocations",
              "tax_lines",
              "duties"
            ],
            "title": "LineItem",
            "type": "object"
          },
          "title": "Line Items",
          "type": "array"
        },
        "location_id": {
          "default": None,
          "description": "Store location identifier",
          "nullable": True,
          "title": "Location Id",
          "type": "integer"
        },
        "merchant_of_record_app_id": {
          "default": None,
          "description": "App handling merchant-of-record functions",
          "nullable": True,
          "title": "Merchant Of Record App Id",
          "type": "integer"
        },
        "name": {
          "description": "Order name (e.g., '#1001')",
          "title": "Name",
          "type": "string"
        },
        "note": {
          "default": None,
          "description": "Merchant's notes about the order",
          "nullable": True,
          "title": "Note",
          "type": "string"
        },
        "note_attributes": {
          "description": "Custom key-value metadata",
          "items": {
            "properties": {
              "name": {
                "description": "Attribute identifier",
                "title": "Name",
                "type": "string"
              },
              "value": {
                "description": "Attribute data",
                "title": "Value",
                "type": "string"
              }
            },
            "required": [
              "name",
              "value"
            ],
            "title": "NoteAttribute",
            "type": "object"
          },
          "title": "Note Attributes",
          "type": "array"
        },
        "number": {
          "description": "Sequential order identifier",
          "title": "Number",
          "type": "integer"
        },
        "order_number": {
          "description": "Sequential order number",
          "title": "Order Number",
          "type": "integer"
        },
        "order_status_url": {
          "default": None,
          "description": "Customer-facing order status page",
          "nullable": True,
          "title": "Order Status Url",
          "type": "string"
        },
        "original_total_duties_set": {
          "additionalProperties": False,
          "default": None,
          "description": "Duty charges in shop and presentment currencies",
          "nullable": True,
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "PriceSet",
          "type": "object"
        },
        "payment_gateway_names": {
          "description": "Payment methods used",
          "items": {
            "properties": {}
          },
          "title": "Payment Gateway Names",
          "type": "array"
        },
        "payment_terms": {
          "additionalProperties": True,
          "default": None,
          "description": "Object containing payment arrangement details",
          "nullable": True,
          "title": "Payment Terms",
          "type": "object"
        },
        "phone": {
          "default": None,
          "description": "The customer's phone number",
          "nullable": True,
          "title": "Phone",
          "type": "string"
        },
        "po_number": {
          "default": None,
          "description": "Purchase order reference",
          "nullable": True,
          "title": "Po Number",
          "type": "string"
        },
        "presentment_currency": {
          "description": "Currency code for display (ISO 4217 format)",
          "title": "Presentment Currency",
          "type": "string"
        },
        "processed_at": {
          "default": None,
          "description": "When payment was processed (ISO 8601 format)",
          "nullable": True,
          "title": "Processed At",
          "type": "string"
        },
        "processing_method": {
          "default": None,
          "description": "How the payment was processed",
          "nullable": True,
          "title": "Processing Method",
          "type": "string"
        },
        "reference": {
          "default": None,
          "description": "External reference identifier",
          "nullable": True,
          "title": "Reference",
          "type": "string"
        },
        "referring_site": {
          "default": None,
          "description": "Site that referred the customer",
          "nullable": True,
          "title": "Referring Site",
          "type": "string"
        },
        "refunds": {
          "description": "Associated refund records",
          "items": {
            "properties": {}
          },
          "title": "Refunds",
          "type": "array"
        },
        "shipping_address": {
          "additionalProperties": False,
          "default": None,
          "description": "Destination address",
          "nullable": True,
          "properties": {
            "address1": {
              "default": None,
              "description": "The street address",
              "nullable": True,
              "title": "Address1",
              "type": "string"
            },
            "address2": {
              "default": None,
              "description": "An optional additional field for the street address",
              "nullable": True,
              "title": "Address2",
              "type": "string"
            },
            "city": {
              "default": None,
              "description": "The city, town, or village",
              "nullable": True,
              "title": "City",
              "type": "string"
            },
            "company": {
              "default": None,
              "description": "The company of the person",
              "nullable": True,
              "title": "Company",
              "type": "string"
            },
            "country": {
              "default": None,
              "description": "The name of the country",
              "nullable": True,
              "title": "Country",
              "type": "string"
            },
            "country_code": {
              "default": None,
              "description": "Two-letter code (ISO 3166-1 format)",
              "nullable": True,
              "title": "Country Code",
              "type": "string"
            },
            "first_name": {
              "default": None,
              "description": "Person's first name",
              "nullable": True,
              "title": "First Name",
              "type": "string"
            },
            "last_name": {
              "default": None,
              "description": "Person's last name",
              "nullable": True,
              "title": "Last Name",
              "type": "string"
            },
            "latitude": {
              "default": None,
              "description": "Geographic latitude coordinate",
              "nullable": True,
              "title": "Latitude",
              "type": "string"
            },
            "longitude": {
              "default": None,
              "description": "Geographic longitude coordinate",
              "nullable": True,
              "title": "Longitude",
              "type": "string"
            },
            "name": {
              "default": None,
              "description": "The full name of the person",
              "nullable": True,
              "title": "Name",
              "type": "string"
            },
            "phone": {
              "default": None,
              "description": "Phone number at address",
              "nullable": True,
              "title": "Phone",
              "type": "string"
            },
            "province": {
              "default": None,
              "description": "The name of the region (province, state, prefecture)",
              "nullable": True,
              "title": "Province",
              "type": "string"
            },
            "province_code": {
              "default": None,
              "description": "Alphanumeric abbreviation of the region",
              "nullable": True,
              "title": "Province Code",
              "type": "string"
            },
            "zip": {
              "default": None,
              "description": "Postal code (zip, postcode, or Eircode)",
              "nullable": True,
              "title": "Zip",
              "type": "string"
            }
          },
          "title": "Address",
          "type": "object"
        },
        "shipping_lines": {
          "description": "Shipping method details",
          "items": {
            "properties": {
              "carrier_identifier": {
                "default": None,
                "description": "Carrier code",
                "nullable": True,
                "title": "Carrier Identifier",
                "type": "string"
              },
              "code": {
                "default": None,
                "description": "Service code",
                "nullable": True,
                "title": "Code",
                "type": "string"
              },
              "delivery_category": {
                "default": None,
                "description": "Delivery type classification",
                "nullable": True,
                "title": "Delivery Category",
                "type": "string"
              },
              "discounted_price": {
                "description": "Reduced price",
                "title": "Discounted Price",
                "type": "string"
              },
              "discounted_price_set": {
                "additionalProperties": False,
                "description": "Multi-currency pricing",
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "description": "Amount in the customer's local currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Presentment Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "description": "Amount in the store's base currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Shop Money",
                    "type": "object"
                  }
                },
                "required": [
                  "shop_money",
                  "presentment_money"
                ],
                "title": "Discounted Price Set",
                "type": "object"
              },
              "id": {
                "description": "Line identifier",
                "title": "Id",
                "type": "integer"
              },
              "phone": {
                "default": None,
                "description": "Contact number",
                "nullable": True,
                "title": "Phone",
                "type": "string"
              },
              "price": {
                "description": "Original shipping cost",
                "title": "Price",
                "type": "string"
              },
              "price_set": {
                "additionalProperties": False,
                "description": "Shop/presentment currency pricing",
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "description": "Amount in the customer's local currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Presentment Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "description": "Amount in the store's base currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Shop Money",
                    "type": "object"
                  }
                },
                "required": [
                  "shop_money",
                  "presentment_money"
                ],
                "title": "Price Set",
                "type": "object"
              },
              "requested_fulfillment_service_id": {
                "default": None,
                "description": "Service preference",
                "nullable": True,
                "title": "Requested Fulfillment Service Id",
                "type": "integer"
              },
              "source": {
                "default": None,
                "description": "Shipping method origin",
                "nullable": True,
                "title": "Source",
                "type": "string"
              },
              "tax_lines": {
                "description": "Applied taxes",
                "items": {
                  "properties": {}
                },
                "title": "Tax Lines",
                "type": "array"
              },
              "title": {
                "description": "Display name",
                "title": "Title",
                "type": "string"
              }
            },
            "required": [
              "id",
              "discounted_price",
              "discounted_price_set",
              "price",
              "price_set",
              "title",
              "tax_lines"
            ],
            "title": "ShippingLine",
            "type": "object"
          },
          "title": "Shipping Lines",
          "type": "array"
        },
        "source_identifier": {
          "default": None,
          "description": "Source-specific identifier",
          "nullable": True,
          "title": "Source Identifier",
          "type": "string"
        },
        "source_name": {
          "default": None,
          "description": "Order source channel",
          "nullable": True,
          "title": "Source Name",
          "type": "string"
        },
        "source_url": {
          "default": None,
          "description": "URL of order source",
          "nullable": True,
          "title": "Source Url",
          "type": "string"
        },
        "subtotal_price": {
          "description": "Total before taxes and shipping",
          "title": "Subtotal Price",
          "type": "string"
        },
        "subtotal_price_set": {
          "additionalProperties": False,
          "description": "Subtotal in both currencies",
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "Subtotal Price Set",
          "type": "object"
        },
        "tags": {
          "default": None,
          "description": "Merchant-assigned tags",
          "nullable": True,
          "title": "Tags",
          "type": "string"
        },
        "tax_lines": {
          "description": "Individual taxes applied to the order",
          "items": {
            "properties": {
              "channel_liable": {
                "default": None,
                "description": "Whether the channel submitting the tax line is liable for remitting",
                "nullable": True,
                "title": "Channel Liable",
                "type": "boolean"
              },
              "price": {
                "description": "Amount added to order after discounts",
                "title": "Price",
                "type": "string"
              },
              "price_set": {
                "additionalProperties": False,
                "description": "Tax amount in shop and presentment currencies",
                "properties": {
                  "presentment_money": {
                    "additionalProperties": False,
                    "description": "Amount in the customer's local currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Presentment Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": False,
                    "description": "Amount in the store's base currency",
                    "properties": {
                      "amount": {
                        "description": "Monetary amount",
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "description": "Currency code (ISO 4217 format)",
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "required": [
                      "amount",
                      "currency_code"
                    ],
                    "title": "Shop Money",
                    "type": "object"
                  }
                },
                "required": [
                  "shop_money",
                  "presentment_money"
                ],
                "title": "Price Set",
                "type": "object"
              },
              "rate": {
                "description": "The tax rate applied to the order to calculate the tax price",
                "title": "Rate",
                "type": "number"
              },
              "title": {
                "description": "The name of the tax",
                "title": "Title",
                "type": "string"
              }
            },
            "required": [
              "title",
              "price",
              "price_set",
              "rate"
            ],
            "title": "TaxLine",
            "type": "object"
          },
          "title": "Tax Lines",
          "type": "array"
        },
        "taxes_included": {
          "description": "Whether prices include taxes",
          "title": "Taxes Included",
          "type": "boolean"
        },
        "test": {
          "description": "Whether order is a test transaction",
          "title": "Test",
          "type": "boolean"
        },
        "token": {
          "description": "Unique token for the order",
          "title": "Token",
          "type": "string"
        },
        "total_discounts": {
          "description": "Total discount amount applied",
          "title": "Total Discounts",
          "type": "string"
        },
        "total_discounts_set": {
          "additionalProperties": False,
          "description": "Discounts in both currencies",
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "Total Discounts Set",
          "type": "object"
        },
        "total_line_items_price": {
          "description": "Line items total before discounts",
          "title": "Total Line Items Price",
          "type": "string"
        },
        "total_line_items_price_set": {
          "additionalProperties": False,
          "description": "Line items total in both currencies",
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "Total Line Items Price Set",
          "type": "object"
        },
        "total_price": {
          "description": "The sum of all line item prices",
          "title": "Total Price",
          "type": "string"
        },
        "total_price_set": {
          "additionalProperties": False,
          "description": "Price in shop and presentment currencies",
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "Total Price Set",
          "type": "object"
        },
        "total_price_usd": {
          "default": None,
          "description": "Order total in USD",
          "nullable": True,
          "title": "Total Price Usd",
          "type": "string"
        },
        "total_shipping_price_set": {
          "additionalProperties": False,
          "description": "Shipping costs in dual currencies",
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "Total Shipping Price Set",
          "type": "object"
        },
        "total_tax": {
          "description": "Sum of prices for all tax lines",
          "title": "Total Tax",
          "type": "string"
        },
        "total_tax_set": {
          "additionalProperties": False,
          "description": "Tax total in both currencies",
          "properties": {
            "presentment_money": {
              "additionalProperties": False,
              "description": "Amount in the customer's local currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Presentment Money",
              "type": "object"
            },
            "shop_money": {
              "additionalProperties": False,
              "description": "Amount in the store's base currency",
              "properties": {
                "amount": {
                  "description": "Monetary amount",
                  "title": "Amount",
                  "type": "string"
                },
                "currency_code": {
                  "description": "Currency code (ISO 4217 format)",
                  "title": "Currency Code",
                  "type": "string"
                }
              },
              "required": [
                "amount",
                "currency_code"
              ],
              "title": "Shop Money",
              "type": "object"
            }
          },
          "required": [
            "shop_money",
            "presentment_money"
          ],
          "title": "Total Tax Set",
          "type": "object"
        },
        "total_weight": {
          "description": "Combined weight of all items in grams",
          "title": "Total Weight",
          "type": "integer"
        },
        "updated_at": {
          "description": "Timestamp of last modification (ISO 8601 format)",
          "title": "Updated At",
          "type": "string"
        },
        "user_id": {
          "default": None,
          "description": "Associated user/staff member ID",
          "nullable": True,
          "title": "User Id",
          "type": "integer"
        }
      },
      "required": [
        "id",
        "created_at",
        "updated_at",
        "number",
        "name",
        "token",
        "test",
        "financial_status",
        "total_price",
        "subtotal_price",
        "total_tax",
        "total_discounts",
        "total_line_items_price",
        "presentment_currency",
        "currency",
        "total_price_set",
        "subtotal_price_set",
        "total_tax_set",
        "total_discounts_set",
        "total_line_items_price_set",
        "total_shipping_price_set",
        "total_weight",
        "fulfillments",
        "shipping_lines",
        "buyer_accepts_marketing",
        "line_items",
        "discount_applications",
        "discount_codes",
        "tax_lines",
        "taxes_included",
        "confirmed",
        "note_attributes",
        "order_number",
        "payment_gateway_names",
        "refunds",
        "admin_graphql_api_id"
      ],
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "UpdateOrderResponseWrapper",
  "type": "object"
}

SHOPIFY_GET_ORDERSBY_ID_OUTPUT_SCHEMA = json.loads(
  """{  "properties": {    "data": {      "additionalProperties": false,      "description": "Data from the action execution",      "properties": {        "admin_graphql_api_id": {          "default": null,          "description": "The GraphQL API identifier for the order.",          "nullable": true,          "title": "Admin Graphql Api Id",          "type": "string"        },        "app_id": {          "default": null,          "description": "The ID of the app that created the order.",          "nullable": true,          "title": "App Id",          "type": "integer"        },        "billing_address": {          "additionalProperties": false,          "default": null,          "description": "Represents a mailing address.",          "nullable": true,          "properties": {            "address1": {              "default": null,              "description": "The first line of the address.",              "nullable": true,              "title": "Address1",              "type": "string"            },            "address2": {              "default": null,              "description": "The second line of the address.",              "nullable": true,              "title": "Address2",              "type": "string"            },            "city": {              "default": null,              "description": "The city of the address.",              "nullable": true,              "title": "City",              "type": "string"            },            "company": {              "default": null,              "description": "The company name.",              "nullable": true,              "title": "Company",              "type": "string"            },            "country": {              "default": null,              "description": "The country of the address.",              "nullable": true,              "title": "Country",              "type": "string"            },            "country_code": {              "default": null,              "description": "The country code in ISO 3166-1 alpha-2 format.",              "nullable": true,              "title": "Country Code",              "type": "string"            },            "first_name": {              "default": null,              "description": "The first name.",              "nullable": true,              "title": "First Name",              "type": "string"            },            "last_name": {              "default": null,              "description": "The last name.",              "nullable": true,              "title": "Last Name",              "type": "string"            },            "latitude": {              "default": null,              "description": "The latitude coordinate.",              "nullable": true,              "title": "Latitude",              "type": "string"            },            "longitude": {              "default": null,              "description": "The longitude coordinate.",              "nullable": true,              "title": "Longitude",              "type": "string"            },            "name": {              "default": null,              "description": "The full name.",              "nullable": true,              "title": "Name",              "type": "string"            },            "phone": {              "default": null,              "description": "The phone number.",              "nullable": true,              "title": "Phone",              "type": "string"            },            "province": {              "default": null,              "description": "The province or state.",              "nullable": true,              "title": "Province",              "type": "string"            },            "province_code": {              "default": null,              "description": "The province or state code.",              "nullable": true,              "title": "Province Code",              "type": "string"            },            "zip": {              "default": null,              "description": "The postal or ZIP code.",              "nullable": true,              "title": "Zip",              "type": "string"            }          },          "title": "Address",          "type": "object"        },        "browser_ip": {          "default": null,          "description": "The IP address of the browser used by the customer when they placed the order. Supports both IPv4 and IPv6.",          "nullable": true,          "title": "Browser Ip",          "type": "string"        },        "buyer_accepts_marketing": {          "default": null,          "description": "Whether the customer consented to receive email updates from the shop.",          "nullable": true,          "title": "Buyer Accepts Marketing",          "type": "boolean"        },        "cancel_reason": {          "default": null,          "description": "The reason why the order was canceled. Valid values: customer, fraud, inventory, declined, other.",          "nullable": true,          "title": "Cancel Reason",          "type": "string"        },        "cancelled_at": {          "default": null,          "description": "The date and time when the order was canceled in ISO 8601 format. Returns null if the order isn't canceled.",          "nullable": true,          "title": "Cancelled At",          "type": "string"        },        "cart_token": {          "default": null,          "description": "Unique identifier for the cart. Deprecated field.",          "nullable": true,          "title": "Cart Token",          "type": "string"        },        "checkout_id": {          "default": null,          "description": "The ID of the checkout associated with the order.",          "nullable": true,          "title": "Checkout Id",          "type": "integer"        },        "checkout_token": {          "default": null,          "description": "Unique identifier for the checkout. Deprecated field.",          "nullable": true,          "title": "Checkout Token",          "type": "string"        },        "client_details": {          "additionalProperties": false,          "default": null,          "description": "Information about the browser that the customer used when they placed their order.",          "nullable": true,          "properties": {            "accept_language": {              "default": null,              "description": "The accepted language of the browser.",              "nullable": true,              "title": "Accept Language",              "type": "string"            },            "browser_height": {              "default": null,              "description": "The browser screen height in pixels.",              "nullable": true,              "title": "Browser Height",              "type": "integer"            },            "browser_ip": {              "default": null,              "description": "The IP address of the browser.",              "nullable": true,              "title": "Browser Ip",              "type": "string"            },            "browser_width": {              "default": null,              "description": "The browser screen width in pixels.",              "nullable": true,              "title": "Browser Width",              "type": "integer"            },            "session_hash": {              "default": null,              "description": "A hash of the session.",              "nullable": true,              "title": "Session Hash",              "type": "string"            },            "user_agent": {              "default": null,              "description": "The user agent string from the browser.",              "nullable": true,              "title": "User Agent",              "type": "string"            }          },          "title": "ClientDetails",          "type": "object"        },        "closed_at": {          "default": null,          "description": "The date and time when the order was closed in ISO 8601 format. Returns null if the order isn't closed.",          "nullable": true,          "title": "Closed At",          "type": "string"        },        "company": {          "additionalProperties": true,          "default": null,          "description": "Information about the company associated with the order for B2B orders. Returns null if not a B2B order.",          "nullable": true,          "title": "Company",          "type": "object"        },        "confirmation_number": {          "default": null,          "description": "A randomly generated alpha-numeric identifier for the order that may be shown to the customer.",          "nullable": true,          "title": "Confirmation Number",          "type": "string"        },        "contact_email": {          "default": null,          "description": "The customer's email address.",          "nullable": true,          "title": "Contact Email",          "type": "string"        },        "created_at": {          "description": "The date and time when the order was created in ISO 8601 format.",          "title": "Created At",          "type": "string"        },        "currency": {          "description": "The three-letter code (ISO 4217 format) for the shop currency.",          "title": "Currency",          "type": "string"        },        "current_subtotal_price": {          "default": null,          "description": "The current subtotal price of the order in the shop currency after returns, refunds, order edits, and cancellations.",          "nullable": true,          "title": "Current Subtotal Price",          "type": "string"        },        "current_subtotal_price_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "current_total_discounts": {          "default": null,          "description": "The current total discounts on the order in the shop currency after returns, refunds, order edits, and cancellations.",          "nullable": true,          "title": "Current Total Discounts",          "type": "string"        },        "current_total_discounts_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "current_total_duties_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Price representation in shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "current_total_price": {          "default": null,          "description": "The current total price of the order in the shop currency after returns, refunds, order edits, and cancellations.",          "nullable": true,          "title": "Current Total Price",          "type": "string"        },        "current_total_price_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "current_total_tax": {          "default": null,          "description": "The current total tax on the order in the shop currency after returns, refunds, order edits, and cancellations.",          "nullable": true,          "title": "Current Total Tax",          "type": "string"        },        "current_total_tax_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "customer": {          "additionalProperties": true,          "default": null,          "description": "Information about the customer. May be null for POS orders.",          "nullable": true,          "title": "Customer",          "type": "object"        },        "customer_locale": {          "default": null,          "description": "The two-letter language code for the customer's locale.",          "nullable": true,          "title": "Customer Locale",          "type": "string"        },        "device_id": {          "default": null,          "description": "The ID of the device that created the order.",          "nullable": true,          "title": "Device Id",          "type": "integer"        },        "discount_applications": {          "default": null,          "description": "List of discount applications.",          "items": {            "additionalProperties": true,            "properties": {},            "type": "object"          },          "nullable": true,          "title": "Discount Applications",          "type": "array"        },        "discount_codes": {          "default": null,          "description": "List of discount codes applied to the order.",          "items": {            "description": "Represents a discount code applied to the order.",            "properties": {              "amount": {                "default": null,                "description": "The amount of the discount.",                "nullable": true,                "title": "Amount",                "type": "string"              },              "code": {                "default": null,                "description": "The discount code.",                "nullable": true,                "title": "Code",                "type": "string"              },              "type": {                "default": null,                "description": "The type of discount. Valid values: fixed_amount, percentage, shipping.",                "nullable": true,                "title": "Type",                "type": "string"              }            },            "title": "DiscountCode",            "type": "object"          },          "nullable": true,          "title": "Discount Codes",          "type": "array"        },        "email": {          "default": null,          "description": "The customer's email address.",          "nullable": true,          "title": "Email",          "type": "string"        },        "estimated_taxes": {          "default": null,          "description": "Whether taxes on the order are estimated.",          "nullable": true,          "title": "Estimated Taxes",          "type": "boolean"        },        "financial_status": {          "default": null,          "description": "The status of payments associated with the order. Valid values: pending, authorized, partially_paid, paid, partially_refunded, refunded, voided.",          "nullable": true,          "title": "Financial Status",          "type": "string"        },        "fulfillment_status": {          "default": null,          "description": "The order's status in terms of fulfilled line items. Valid values: fulfilled, partial, restocked, null (unfulfilled).",          "nullable": true,          "title": "Fulfillment Status",          "type": "string"        },        "fulfillments": {          "default": null,          "description": "Array of fulfillment objects for the order.",          "items": {            "additionalProperties": true,            "properties": {},            "type": "object"          },          "nullable": true,          "title": "Fulfillments",          "type": "array"        },        "gateway": {          "default": null,          "description": "The payment gateway used for the order.",          "nullable": true,          "title": "Gateway",          "type": "string"        },        "id": {          "description": "Unique identifier for the order.",          "title": "Id",          "type": "integer"        },        "landing_site": {          "default": null,          "description": "The URL for the page where the buyer landed when entering the shop.",          "nullable": true,          "title": "Landing Site",          "type": "string"        },        "landing_site_ref": {          "default": null,          "description": "The landing site referrer.",          "nullable": true,          "title": "Landing Site Ref",          "type": "string"        },        "line_items": {          "description": "A list of line item objects, each containing information about an item in the order.",          "items": {            "description": "Represents an item in the order.",            "properties": {              "attributed_staffs": {                "default": null,                "description": "Staff members attributed to the line item.",                "items": {                  "additionalProperties": true,                  "properties": {},                  "type": "object"                },                "nullable": true,                "title": "Attributed Staffs",                "type": "array"              },              "current_quantity": {                "default": null,                "description": "The current quantity after removals.",                "nullable": true,                "title": "Current Quantity",                "type": "integer"              },              "discount_allocations": {                "default": null,                "description": "List of discount allocations.",                "items": {                  "additionalProperties": true,                  "properties": {},                  "type": "object"                },                "nullable": true,                "title": "Discount Allocations",                "type": "array"              },              "duties": {                "default": null,                "description": "List of duties applied to the line item.",                "items": {                  "additionalProperties": true,                  "properties": {},                  "type": "object"                },                "nullable": true,                "title": "Duties",                "type": "array"              },              "fulfillable_quantity": {                "default": null,                "description": "The amount available to fulfill.",                "nullable": true,                "title": "Fulfillable Quantity",                "type": "integer"              },              "fulfillment_service": {                "default": null,                "description": "The service provider fulfilling the item.",                "nullable": true,                "title": "Fulfillment Service",                "type": "string"              },              "fulfillment_status": {                "default": null,                "description": "The fulfillment status of the line item.",                "nullable": true,                "title": "Fulfillment Status",                "type": "string"              },              "gift_card": {                "default": null,                "description": "Whether the line item is a gift card.",                "nullable": true,                "title": "Gift Card",                "type": "boolean"              },              "grams": {                "default": null,                "description": "The weight of the item in grams.",                "nullable": true,                "title": "Grams",                "type": "integer"              },              "id": {                "description": "The ID of the line item.",                "title": "Id",                "type": "integer"              },              "name": {                "description": "The name of the product variant.",                "title": "Name",                "type": "string"              },              "origin_location": {                "additionalProperties": true,                "default": null,                "description": "The location from where the item is being fulfilled.",                "nullable": true,                "title": "Origin Location",                "type": "object"              },              "price": {                "description": "The price of the item.",                "title": "Price",                "type": "string"              },              "price_set": {                "additionalProperties": false,                "default": null,                "description": "Price representation in shop and presentment currencies.",                "nullable": true,                "properties": {                  "presentment_money": {                    "additionalProperties": false,                    "default": null,                    "description": "Represents an amount in both shop and presentment currencies.",                    "nullable": true,                    "properties": {                      "amount": {                        "default": null,                        "description": "The decimal amount.",                        "nullable": true,                        "title": "Amount",                        "type": "string"                      },                      "currency_code": {                        "default": null,                        "description": "The currency code.",                        "nullable": true,                        "title": "Currency Code",                        "type": "string"                      }                    },                    "title": "MoneySet",                    "type": "object"                  },                  "shop_money": {                    "additionalProperties": false,                    "default": null,                    "description": "Represents an amount in both shop and presentment currencies.",                    "nullable": true,                    "properties": {                      "amount": {                        "default": null,                        "description": "The decimal amount.",                        "nullable": true,                        "title": "Amount",                        "type": "string"                      },                      "currency_code": {                        "default": null,                        "description": "The currency code.",                        "nullable": true,                        "title": "Currency Code",                        "type": "string"                      }                    },                    "title": "MoneySet",                    "type": "object"                  }                },                "title": "PriceSet",                "type": "object"              },              "product_id": {                "default": null,                "description": "The ID of the product.",                "nullable": true,                "title": "Product Id",                "type": "integer"              },              "properties": {                "default": null,                "description": "Custom properties for the line item.",                "items": {                  "additionalProperties": true,                  "properties": {},                  "type": "object"                },                "nullable": true,                "title": "Properties",                "type": "array"              },              "quantity": {                "description": "The number of items purchased.",                "title": "Quantity",                "type": "integer"              },              "requires_shipping": {                "default": null,                "description": "Whether the line item requires shipping.",                "nullable": true,                "title": "Requires Shipping",                "type": "boolean"              },              "sku": {                "default": null,                "description": "The SKU of the product variant.",                "nullable": true,                "title": "Sku",                "type": "string"              },              "tax_lines": {                "default": null,                "description": "List of tax line objects.",                "items": {                  "additionalProperties": true,                  "properties": {},                  "type": "object"                },                "nullable": true,                "title": "Tax Lines",                "type": "array"              },              "taxable": {                "default": null,                "description": "Whether the line item is taxable.",                "nullable": true,                "title": "Taxable",                "type": "boolean"              },              "tip_payment_gateway": {                "default": null,                "description": "The payment gateway used to tender the tip.",                "nullable": true,                "title": "Tip Payment Gateway",                "type": "string"              },              "tip_payment_method": {                "default": null,                "description": "The payment method used for the tip.",                "nullable": true,                "title": "Tip Payment Method",                "type": "string"              },              "title": {                "description": "The title of the product.",                "title": "Title",                "type": "string"              },              "total_discount": {                "default": null,                "description": "The total discount amount applied to the line item.",                "nullable": true,                "title": "Total Discount",                "type": "string"              },              "total_discount_set": {                "additionalProperties": false,                "default": null,                "description": "Price representation in shop and presentment currencies.",                "nullable": true,                "properties": {                  "presentment_money": {                    "additionalProperties": false,                    "default": null,                    "description": "Represents an amount in both shop and presentment currencies.",                    "nullable": true,                    "properties": {                      "amount": {                        "default": null,                        "description": "The decimal amount.",                        "nullable": true,                        "title": "Amount",                        "type": "string"                      },                      "currency_code": {                        "default": null,                        "description": "The currency code.",                        "nullable": true,                        "title": "Currency Code",                        "type": "string"                      }                    },                    "title": "MoneySet",                    "type": "object"                  },                  "shop_money": {                    "additionalProperties": false,                    "default": null,                    "description": "Represents an amount in both shop and presentment currencies.",                    "nullable": true,                    "properties": {                      "amount": {                        "default": null,                        "description": "The decimal amount.",                        "nullable": true,                        "title": "Amount",                        "type": "string"                      },                      "currency_code": {                        "default": null,                        "description": "The currency code.",                        "nullable": true,                        "title": "Currency Code",                        "type": "string"                      }                    },                    "title": "MoneySet",                    "type": "object"                  }                },                "title": "PriceSet",                "type": "object"              },              "variant_id": {                "default": null,                "description": "The ID of the product variant.",                "nullable": true,                "title": "Variant Id",                "type": "integer"              },              "variant_title": {                "default": null,                "description": "The title of the product variant.",                "nullable": true,                "title": "Variant Title",                "type": "string"              },              "vendor": {                "default": null,                "description": "The vendor of the product.",                "nullable": true,                "title": "Vendor",                "type": "string"              }            },            "required": [              "id",              "title",              "name",              "quantity",              "price"            ],            "title": "LineItem",            "type": "object"          },          "title": "Line Items",          "type": "array"        },        "location_id": {          "default": null,          "description": "The ID of the physical location where the order was processed.",          "nullable": true,          "title": "Location Id",          "type": "integer"        },        "name": {          "description": "The order name, which is a unique identifier starting with #.",          "title": "Name",          "type": "string"        },        "note": {          "default": null,          "description": "An optional note attached to the order.",          "nullable": true,          "title": "Note",          "type": "string"        },        "note_attributes": {          "default": null,          "description": "Extra information added to the order by the customer.",          "items": {            "description": "Extra information added to the order by the customer.",            "properties": {              "name": {                "default": null,                "description": "The attribute name.",                "nullable": true,                "title": "Name",                "type": "string"              },              "value": {                "default": null,                "description": "The attribute value.",                "nullable": true,                "title": "Value",                "type": "string"              }            },            "title": "NoteAttribute",            "type": "object"          },          "nullable": true,          "title": "Note Attributes",          "type": "array"        },        "number": {          "description": "The sequential order number, used for display purposes.",          "title": "Number",          "type": "integer"        },        "order_number": {          "description": "The order's position in the shop's order list.",          "title": "Order Number",          "type": "integer"        },        "order_status_url": {          "default": null,          "description": "The URL pointing to the order status web page.",          "nullable": true,          "title": "Order Status Url",          "type": "string"        },        "original_total_duties_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "payment_gateway_names": {          "default": null,          "description": "The list of payment gateways used for the order.",          "items": {            "properties": {},            "type": "string"          },          "nullable": true,          "title": "Payment Gateway Names",          "type": "array"        },        "phone": {          "default": null,          "description": "The customer's phone number.",          "nullable": true,          "title": "Phone",          "type": "string"        },        "presentment_currency": {          "default": null,          "description": "The three-letter code (ISO 4217 format) for the currency that the customer used at checkout.",          "nullable": true,          "title": "Presentment Currency",          "type": "string"        },        "processed_at": {          "default": null,          "description": "The date and time when the order was processed in ISO 8601 format.",          "nullable": true,          "title": "Processed At",          "type": "string"        },        "processing_method": {          "default": null,          "description": "The payment processing method. Valid values: checkout, direct, manual, offsite, express.",          "nullable": true,          "title": "Processing Method",          "type": "string"        },        "reference": {          "default": null,          "description": "The reference number for the order.",          "nullable": true,          "title": "Reference",          "type": "string"        },        "referring_site": {          "default": null,          "description": "The website that the customer clicked on to come to the shop.",          "nullable": true,          "title": "Referring Site",          "type": "string"        },        "refunds": {          "default": null,          "description": "List of refunds applied to the order.",          "items": {            "additionalProperties": true,            "properties": {},            "type": "object"          },          "nullable": true,          "title": "Refunds",          "type": "array"        },        "shipping_address": {          "additionalProperties": false,          "default": null,          "description": "Represents a mailing address.",          "nullable": true,          "properties": {            "address1": {              "default": null,              "description": "The first line of the address.",              "nullable": true,              "title": "Address1",              "type": "string"            },            "address2": {              "default": null,              "description": "The second line of the address.",              "nullable": true,              "title": "Address2",              "type": "string"            },            "city": {              "default": null,              "description": "The city of the address.",              "nullable": true,              "title": "City",              "type": "string"            },            "company": {              "default": null,              "description": "The company name.",              "nullable": true,              "title": "Company",              "type": "string"            },            "country": {              "default": null,              "description": "The country of the address.",              "nullable": true,              "title": "Country",              "type": "string"            },            "country_code": {              "default": null,              "description": "The country code in ISO 3166-1 alpha-2 format.",              "nullable": true,              "title": "Country Code",              "type": "string"            },            "first_name": {              "default": null,              "description": "The first name.",              "nullable": true,              "title": "First Name",              "type": "string"            },            "last_name": {              "default": null,              "description": "The last name.",              "nullable": true,              "title": "Last Name",              "type": "string"            },            "latitude": {              "default": null,              "description": "The latitude coordinate.",              "nullable": true,              "title": "Latitude",              "type": "string"            },            "longitude": {              "default": null,              "description": "The longitude coordinate.",              "nullable": true,              "title": "Longitude",              "type": "string"            },            "name": {              "default": null,              "description": "The full name.",              "nullable": true,              "title": "Name",              "type": "string"            },            "phone": {              "default": null,              "description": "The phone number.",              "nullable": true,              "title": "Phone",              "type": "string"            },            "province": {              "default": null,              "description": "The province or state.",              "nullable": true,              "title": "Province",              "type": "string"            },            "province_code": {              "default": null,              "description": "The province or state code.",              "nullable": true,              "title": "Province Code",              "type": "string"            },            "zip": {              "default": null,              "description": "The postal or ZIP code.",              "nullable": true,              "title": "Zip",              "type": "string"            }          },          "title": "Address",          "type": "object"        },        "shipping_lines": {          "default": null,          "description": "Array of shipping line objects, each containing information about the shipping methods used.",          "items": {            "description": "Represents a shipping method used for the order.",            "properties": {              "carrier_identifier": {                "default": null,                "description": "A reference to the carrier service.",                "nullable": true,                "title": "Carrier Identifier",                "type": "string"              },              "code": {                "default": null,                "description": "A reference to the shipping method.",                "nullable": true,                "title": "Code",                "type": "string"              },              "discount_allocations": {                "default": null,                "description": "List of discount allocations for the shipping line.",                "items": {                  "additionalProperties": true,                  "properties": {},                  "type": "object"                },                "nullable": true,                "title": "Discount Allocations",                "type": "array"              },              "id": {                "default": null,                "description": "The ID of the shipping line.",                "nullable": true,                "title": "Id",                "type": "integer"              },              "price": {                "default": null,                "description": "The price of the shipping method.",                "nullable": true,                "title": "Price",                "type": "string"              },              "price_set": {                "additionalProperties": false,                "default": null,                "description": "Price representation in shop and presentment currencies.",                "nullable": true,                "properties": {                  "presentment_money": {                    "additionalProperties": false,                    "default": null,                    "description": "Represents an amount in both shop and presentment currencies.",                    "nullable": true,                    "properties": {                      "amount": {                        "default": null,                        "description": "The decimal amount.",                        "nullable": true,                        "title": "Amount",                        "type": "string"                      },                      "currency_code": {                        "default": null,                        "description": "The currency code.",                        "nullable": true,                        "title": "Currency Code",                        "type": "string"                      }                    },                    "title": "MoneySet",                    "type": "object"                  },                  "shop_money": {                    "additionalProperties": false,                    "default": null,                    "description": "Represents an amount in both shop and presentment currencies.",                    "nullable": true,                    "properties": {                      "amount": {                        "default": null,                        "description": "The decimal amount.",                        "nullable": true,                        "title": "Amount",                        "type": "string"                      },                      "currency_code": {                        "default": null,                        "description": "The currency code.",                        "nullable": true,                        "title": "Currency Code",                        "type": "string"                      }                    },                    "title": "MoneySet",                    "type": "object"                  }                },                "title": "PriceSet",                "type": "object"              },              "requested_fulfillment_service_id": {                "default": null,                "description": "The ID of the fulfillment service.",                "nullable": true,                "title": "Requested Fulfillment Service Id",                "type": "string"              },              "source": {                "default": null,                "description": "The source of the shipping method.",                "nullable": true,                "title": "Source",                "type": "string"              },              "tax_lines": {                "default": null,                "description": "List of tax line objects for the shipping line.",                "items": {                  "additionalProperties": true,                  "properties": {},                  "type": "object"                },                "nullable": true,                "title": "Tax Lines",                "type": "array"              },              "title": {                "default": null,                "description": "The title of the shipping method.",                "nullable": true,                "title": "Title",                "type": "string"              }            },            "title": "ShippingLine",            "type": "object"          },          "nullable": true,          "title": "Shipping Lines",          "type": "array"        },        "source_identifier": {          "default": null,          "description": "The ID of the order source.",          "nullable": true,          "title": "Source Identifier",          "type": "string"        },        "source_name": {          "default": null,          "description": "Where the order originated. Valid values: web, pos, mobile, draft_order.",          "nullable": true,          "title": "Source Name",          "type": "string"        },        "source_url": {          "default": null,          "description": "The URL of the order source.",          "nullable": true,          "title": "Source Url",          "type": "string"        },        "subtotal_price": {          "default": null,          "description": "The price of the order before shipping and taxes.",          "nullable": true,          "title": "Subtotal Price",          "type": "string"        },        "subtotal_price_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "tags": {          "default": null,          "description": "Tags attached to the order, formatted as a string of comma-separated values.",          "nullable": true,          "title": "Tags",          "type": "string"        },        "tax_lines": {          "default": null,          "description": "Array of tax line objects, each of which details a tax applied to the order.",          "items": {            "description": "Represents a tax applied to the order.",            "properties": {              "channel_liable": {                "default": null,                "description": "Whether the channel is liable for the tax.",                "nullable": true,                "title": "Channel Liable",                "type": "boolean"              },              "price": {                "default": null,                "description": "The amount of tax to be charged.",                "nullable": true,                "title": "Price",                "type": "string"              },              "price_set": {                "additionalProperties": false,                "default": null,                "description": "Price representation in shop and presentment currencies.",                "nullable": true,                "properties": {                  "presentment_money": {                    "additionalProperties": false,                    "default": null,                    "description": "Represents an amount in both shop and presentment currencies.",                    "nullable": true,                    "properties": {                      "amount": {                        "default": null,                        "description": "The decimal amount.",                        "nullable": true,                        "title": "Amount",                        "type": "string"                      },                      "currency_code": {                        "default": null,                        "description": "The currency code.",                        "nullable": true,                        "title": "Currency Code",                        "type": "string"                      }                    },                    "title": "MoneySet",                    "type": "object"                  },                  "shop_money": {                    "additionalProperties": false,                    "default": null,                    "description": "Represents an amount in both shop and presentment currencies.",                    "nullable": true,                    "properties": {                      "amount": {                        "default": null,                        "description": "The decimal amount.",                        "nullable": true,                        "title": "Amount",                        "type": "string"                      },                      "currency_code": {                        "default": null,                        "description": "The currency code.",                        "nullable": true,                        "title": "Currency Code",                        "type": "string"                      }                    },                    "title": "MoneySet",                    "type": "object"                  }                },                "title": "PriceSet",                "type": "object"              },              "rate": {                "default": null,                "description": "The tax rate applied.",                "nullable": true,                "title": "Rate",                "type": "number"              },              "title": {                "default": null,                "description": "The name of the tax.",                "nullable": true,                "title": "Title",                "type": "string"              }            },            "title": "TaxLine",            "type": "object"          },          "nullable": true,          "title": "Tax Lines",          "type": "array"        },        "taxes_included": {          "default": null,          "description": "Whether taxes are included in the order subtotal.",          "nullable": true,          "title": "Taxes Included",          "type": "boolean"        },        "test": {          "default": null,          "description": "Whether this is a test order.",          "nullable": true,          "title": "Test",          "type": "boolean"        },        "token": {          "description": "A unique token for the order.",          "title": "Token",          "type": "string"        },        "total_discounts": {          "default": null,          "description": "The total discounts applied to the order.",          "nullable": true,          "title": "Total Discounts",          "type": "string"        },        "total_discounts_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "total_line_items_price": {          "default": null,          "description": "The sum of all line item prices before discounts.",          "nullable": true,          "title": "Total Line Items Price",          "type": "string"        },        "total_line_items_price_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "total_outstanding": {          "default": null,          "description": "The total outstanding amount of the order.",          "nullable": true,          "title": "Total Outstanding",          "type": "string"        },        "total_price": {          "description": "The sum of all line item prices, discounts, shipping, and taxes for the order.",          "title": "Total Price",          "type": "string"        },        "total_price_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "total_shipping_price_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "total_tax": {          "default": null,          "description": "The sum of all taxes applied to the order.",          "nullable": true,          "title": "Total Tax",          "type": "string"        },        "total_tax_set": {          "additionalProperties": false,          "default": null,          "description": "Price representation in shop and presentment currencies.",          "nullable": true,          "properties": {            "presentment_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            },            "shop_money": {              "additionalProperties": false,              "default": null,              "description": "Represents an amount in both shop and presentment currencies.",              "nullable": true,              "properties": {                "amount": {                  "default": null,                  "description": "The decimal amount.",                  "nullable": true,                  "title": "Amount",                  "type": "string"                },                "currency_code": {                  "default": null,                  "description": "The currency code.",                  "nullable": true,                  "title": "Currency Code",                  "type": "string"                }              },              "title": "MoneySet",              "type": "object"            }          },          "title": "PriceSet",          "type": "object"        },        "total_tip_received": {          "default": null,          "description": "The total tip amount received for the order.",          "nullable": true,          "title": "Total Tip Received",          "type": "string"        },        "total_weight": {          "default": null,          "description": "The sum of all line item weights in grams.",          "nullable": true,          "title": "Total Weight",          "type": "integer"        },        "updated_at": {          "description": "The date and time when the order was last modified in ISO 8601 format.",          "title": "Updated At",          "type": "string"        },        "user_id": {          "default": null,          "description": "The ID of the user who created the order.",          "nullable": true,          "title": "User Id",          "type": "integer"        }      },      "required": [        "id",        "created_at",        "currency",        "line_items",        "name",        "number",        "order_number",        "token",        "total_price",        "updated_at"      ],      "title": "Data",      "type": "object"    },    "error": {      "default": null,      "description": "Error if any occurred during the execution of the action",      "nullable": true,      "title": "Error",      "type": "string"    },    "successful": {      "description": "Whether or not the action execution was successful or not",      "title": "Successful",      "type": "boolean"    }  },  "required": [    "data",    "successful"  ],  "title": "GetOrdersbyIdResponseWrapper",  "type": "object"}"""
)

SHOPIFY_GET_ORDER_LIST_OUTPUT_SCHEMA = json.loads(
  """{
  "properties": {
    "data": {
      "additionalProperties": false,
      "description": "Data from the action execution",
      "properties": {
        "orders": {
          "description": "Array of order objects returned by the API.",
          "items": {
            "description": "Represents a Shopify order object.",
            "properties": {
              "admin_graphql_api_id": {
                "default": null,
                "description": "The GraphQL API identifier for the order (format: gid://shopify/Order/[ID]).",
                "nullable": true,
                "title": "Admin Graphql Api Id",
                "type": "string"
              },
              "app_id": {
                "default": null,
                "description": "The ID of the app that created the order.",
                "nullable": true,
                "title": "App Id",
                "type": "integer"
              },
              "billing_address": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a mailing address.",
                "nullable": true,
                "properties": {
                  "address1": {
                    "default": null,
                    "description": "Street address line 1.",
                    "nullable": true,
                    "title": "Address1",
                    "type": "string"
                  },
                  "address2": {
                    "default": null,
                    "description": "Street address line 2.",
                    "nullable": true,
                    "title": "Address2",
                    "type": "string"
                  },
                  "city": {
                    "default": null,
                    "description": "City name.",
                    "nullable": true,
                    "title": "City",
                    "type": "string"
                  },
                  "company": {
                    "default": null,
                    "description": "Company name.",
                    "nullable": true,
                    "title": "Company",
                    "type": "string"
                  },
                  "country": {
                    "default": null,
                    "description": "Country name.",
                    "nullable": true,
                    "title": "Country",
                    "type": "string"
                  },
                  "country_code": {
                    "default": null,
                    "description": "Two-letter country code.",
                    "nullable": true,
                    "title": "Country Code",
                    "type": "string"
                  },
                  "first_name": {
                    "default": null,
                    "description": "First name.",
                    "nullable": true,
                    "title": "First Name",
                    "type": "string"
                  },
                  "last_name": {
                    "default": null,
                    "description": "Last name.",
                    "nullable": true,
                    "title": "Last Name",
                    "type": "string"
                  },
                  "latitude": {
                    "default": null,
                    "description": "Latitude coordinate.",
                    "nullable": true,
                    "title": "Latitude",
                    "type": "number"
                  },
                  "longitude": {
                    "default": null,
                    "description": "Longitude coordinate.",
                    "nullable": true,
                    "title": "Longitude",
                    "type": "number"
                  },
                  "name": {
                    "default": null,
                    "description": "Full name.",
                    "nullable": true,
                    "title": "Name",
                    "type": "string"
                  },
                  "phone": {
                    "default": null,
                    "description": "Phone number.",
                    "nullable": true,
                    "title": "Phone",
                    "type": "string"
                  },
                  "province": {
                    "default": null,
                    "description": "Province or state name.",
                    "nullable": true,
                    "title": "Province",
                    "type": "string"
                  },
                  "province_code": {
                    "default": null,
                    "description": "Province or state code.",
                    "nullable": true,
                    "title": "Province Code",
                    "type": "string"
                  },
                  "zip": {
                    "default": null,
                    "description": "Postal or ZIP code.",
                    "nullable": true,
                    "title": "Zip",
                    "type": "string"
                  }
                },
                "title": "Address",
                "type": "object"
              },
              "browser_ip": {
                "default": null,
                "description": "The IP address of the browser used by the customer when they placed the order. Both IPv4 and IPv6 are supported.",
                "nullable": true,
                "title": "Browser Ip",
                "type": "string"
              },
              "buyer_accepts_marketing": {
                "default": null,
                "description": "Whether the customer consented to receive email updates from the shop.",
                "nullable": true,
                "title": "Buyer Accepts Marketing",
                "type": "boolean"
              },
              "cancel_reason": {
                "default": null,
                "description": "The reason why the order was canceled. Valid values: customer, fraud, inventory, declined, other.",
                "nullable": true,
                "title": "Cancel Reason",
                "type": "string"
              },
              "cancelled_at": {
                "default": null,
                "description": "The date and time when the order was canceled in ISO 8601 format. Returns null if the order isn't canceled.",
                "nullable": true,
                "title": "Cancelled At",
                "type": "string"
              },
              "cart_token": {
                "default": null,
                "description": "A unique value when referencing the cart that's associated with the order. Deprecated field.",
                "nullable": true,
                "title": "Cart Token",
                "type": "string"
              },
              "checkout_id": {
                "default": null,
                "description": "The ID of the order placed on the originating platform, such as a unique POS or third-party identifier.",
                "nullable": true,
                "title": "Checkout Id",
                "type": "integer"
              },
              "checkout_token": {
                "default": null,
                "description": "A unique value when referencing the checkout that's associated with the order. Deprecated field.",
                "nullable": true,
                "title": "Checkout Token",
                "type": "string"
              },
              "client_details": {
                "additionalProperties": true,
                "default": null,
                "description": "Information about the browser that the customer used when they placed their order, including user agent and session hash.",
                "nullable": true,
                "title": "Client Details",
                "type": "object"
              },
              "closed_at": {
                "default": null,
                "description": "The date and time when the order was closed in ISO 8601 format. Returns null if the order isn't closed.",
                "nullable": true,
                "title": "Closed At",
                "type": "string"
              },
              "company": {
                "additionalProperties": true,
                "default": null,
                "description": "Represents information about the purchasing company for the order.",
                "nullable": true,
                "title": "Company",
                "type": "object"
              },
              "confirmation_number": {
                "default": null,
                "description": "A randomly generated alpha-numeric identifier for the order.",
                "nullable": true,
                "title": "Confirmation Number",
                "type": "string"
              },
              "confirmed": {
                "default": null,
                "description": "Whether the order has been confirmed.",
                "nullable": true,
                "title": "Confirmed",
                "type": "boolean"
              },
              "contact_email": {
                "default": null,
                "description": "The contact email address for the order.",
                "nullable": true,
                "title": "Contact Email",
                "type": "string"
              },
              "created_at": {
                "default": null,
                "description": "The date and time when the order was created in ISO 8601 format.",
                "nullable": true,
                "title": "Created At",
                "type": "string"
              },
              "currency": {
                "default": null,
                "description": "The three-letter code (ISO 4217) for the shop currency.",
                "nullable": true,
                "title": "Currency",
                "type": "string"
              },
              "current_subtotal_price": {
                "default": null,
                "description": "The current subtotal price of the order in the shop currency, updated according to refunds.",
                "nullable": true,
                "title": "Current Subtotal Price",
                "type": "string"
              },
              "current_subtotal_price_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "current_total_additional_fees_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "current_total_discounts": {
                "default": null,
                "description": "The current total discounts on the order in the shop currency, updated according to refunds.",
                "nullable": true,
                "title": "Current Total Discounts",
                "type": "string"
              },
              "current_total_discounts_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "current_total_duties_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "current_total_price": {
                "default": null,
                "description": "The current total price of the order in the shop currency, updated according to refunds.",
                "nullable": true,
                "title": "Current Total Price",
                "type": "string"
              },
              "current_total_price_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "current_total_tax": {
                "default": null,
                "description": "The current total tax amount for the order.",
                "nullable": true,
                "title": "Current Total Tax",
                "type": "string"
              },
              "current_total_tax_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "customer": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents customer information.",
                "nullable": true,
                "properties": {
                  "accepts_marketing": {
                    "default": null,
                    "description": "Whether the customer has consented to receive marketing material.",
                    "nullable": true,
                    "title": "Accepts Marketing",
                    "type": "boolean"
                  },
                  "accepts_marketing_updated_at": {
                    "default": null,
                    "description": "The date and time when the customer consented or objected to receiving marketing material.",
                    "nullable": true,
                    "title": "Accepts Marketing Updated At",
                    "type": "string"
                  },
                  "admin_graphql_api_id": {
                    "default": null,
                    "description": "The GraphQL API identifier for the customer.",
                    "nullable": true,
                    "title": "Admin Graphql Api Id",
                    "type": "string"
                  },
                  "created_at": {
                    "default": null,
                    "description": "The date and time when the customer was created.",
                    "nullable": true,
                    "title": "Created At",
                    "type": "string"
                  },
                  "currency": {
                    "default": null,
                    "description": "The three-letter code for the currency that the customer used when they paid for their last order.",
                    "nullable": true,
                    "title": "Currency",
                    "type": "string"
                  },
                  "default_address": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a mailing address.",
                    "nullable": true,
                    "properties": {
                      "address1": {
                        "default": null,
                        "description": "Street address line 1.",
                        "nullable": true,
                        "title": "Address1",
                        "type": "string"
                      },
                      "address2": {
                        "default": null,
                        "description": "Street address line 2.",
                        "nullable": true,
                        "title": "Address2",
                        "type": "string"
                      },
                      "city": {
                        "default": null,
                        "description": "City name.",
                        "nullable": true,
                        "title": "City",
                        "type": "string"
                      },
                      "company": {
                        "default": null,
                        "description": "Company name.",
                        "nullable": true,
                        "title": "Company",
                        "type": "string"
                      },
                      "country": {
                        "default": null,
                        "description": "Country name.",
                        "nullable": true,
                        "title": "Country",
                        "type": "string"
                      },
                      "country_code": {
                        "default": null,
                        "description": "Two-letter country code.",
                        "nullable": true,
                        "title": "Country Code",
                        "type": "string"
                      },
                      "first_name": {
                        "default": null,
                        "description": "First name.",
                        "nullable": true,
                        "title": "First Name",
                        "type": "string"
                      },
                      "last_name": {
                        "default": null,
                        "description": "Last name.",
                        "nullable": true,
                        "title": "Last Name",
                        "type": "string"
                      },
                      "latitude": {
                        "default": null,
                        "description": "Latitude coordinate.",
                        "nullable": true,
                        "title": "Latitude",
                        "type": "number"
                      },
                      "longitude": {
                        "default": null,
                        "description": "Longitude coordinate.",
                        "nullable": true,
                        "title": "Longitude",
                        "type": "number"
                      },
                      "name": {
                        "default": null,
                        "description": "Full name.",
                        "nullable": true,
                        "title": "Name",
                        "type": "string"
                      },
                      "phone": {
                        "default": null,
                        "description": "Phone number.",
                        "nullable": true,
                        "title": "Phone",
                        "type": "string"
                      },
                      "province": {
                        "default": null,
                        "description": "Province or state name.",
                        "nullable": true,
                        "title": "Province",
                        "type": "string"
                      },
                      "province_code": {
                        "default": null,
                        "description": "Province or state code.",
                        "nullable": true,
                        "title": "Province Code",
                        "type": "string"
                      },
                      "zip": {
                        "default": null,
                        "description": "Postal or ZIP code.",
                        "nullable": true,
                        "title": "Zip",
                        "type": "string"
                      }
                    },
                    "title": "Address",
                    "type": "object"
                  },
                  "email": {
                    "default": null,
                    "description": "The customer's email address.",
                    "nullable": true,
                    "title": "Email",
                    "type": "string"
                  },
                  "first_name": {
                    "default": null,
                    "description": "The customer's first name.",
                    "nullable": true,
                    "title": "First Name",
                    "type": "string"
                  },
                  "id": {
                    "default": null,
                    "description": "The unique identifier for the customer.",
                    "nullable": true,
                    "title": "Id",
                    "type": "integer"
                  },
                  "last_name": {
                    "default": null,
                    "description": "The customer's last name.",
                    "nullable": true,
                    "title": "Last Name",
                    "type": "string"
                  },
                  "phone": {
                    "default": null,
                    "description": "The customer's phone number.",
                    "nullable": true,
                    "title": "Phone",
                    "type": "string"
                  },
                  "tags": {
                    "default": null,
                    "description": "A comma-separated list of tags that have been added to the customer.",
                    "nullable": true,
                    "title": "Tags",
                    "type": "string"
                  },
                  "updated_at": {
                    "default": null,
                    "description": "The date and time when the customer was last updated.",
                    "nullable": true,
                    "title": "Updated At",
                    "type": "string"
                  }
                },
                "title": "Customer",
                "type": "object"
              },
              "customer_locale": {
                "default": null,
                "description": "The customer's language and region preference at the time of purchase (e.g., 'en', 'fr-CA', 'es-MX').",
                "nullable": true,
                "title": "Customer Locale",
                "type": "string"
              },
              "device_id": {
                "default": null,
                "description": "The device ID, which will include the pos_device_id for POS orders.",
                "nullable": true,
                "title": "Device Id",
                "type": "integer"
              },
              "discount_applications": {
                "default": null,
                "description": "List of discount applications with type, code/title, and amount information.",
                "items": {
                  "description": "Represents a discount application.",
                  "properties": {
                    "allocation_method": {
                      "default": null,
                      "description": "How the discount is allocated (across, each, one).",
                      "nullable": true,
                      "title": "Allocation Method",
                      "type": "string"
                    },
                    "code": {
                      "default": null,
                      "description": "The discount code, if applicable.",
                      "nullable": true,
                      "title": "Code",
                      "type": "string"
                    },
                    "description": {
                      "default": null,
                      "description": "The description of the discount.",
                      "nullable": true,
                      "title": "Description",
                      "type": "string"
                    },
                    "target_selection": {
                      "default": null,
                      "description": "The selection method for line items (all, entitled, explicit).",
                      "nullable": true,
                      "title": "Target Selection",
                      "type": "string"
                    },
                    "target_type": {
                      "default": null,
                      "description": "The type of item the discount applies to (line_item, shipping_line).",
                      "nullable": true,
                      "title": "Target Type",
                      "type": "string"
                    },
                    "title": {
                      "default": null,
                      "description": "The title of the discount or the discount code.",
                      "nullable": true,
                      "title": "Title",
                      "type": "string"
                    },
                    "type": {
                      "default": null,
                      "description": "Type of discount (fixed_amount, percentage, shipping, automatic, discount_code, manual, script).",
                      "nullable": true,
                      "title": "Type",
                      "type": "string"
                    },
                    "value": {
                      "default": null,
                      "description": "The discount value.",
                      "nullable": true,
                      "title": "Value",
                      "type": "string"
                    },
                    "value_type": {
                      "default": null,
                      "description": "The type of discount value (fixed_amount, percentage).",
                      "nullable": true,
                      "title": "Value Type",
                      "type": "string"
                    }
                  },
                  "title": "DiscountApplication",
                  "type": "object"
                },
                "nullable": true,
                "title": "Discount Applications",
                "type": "array"
              },
              "discount_codes": {
                "default": null,
                "description": "Applied discounts with code, amount, and type.",
                "items": {
                  "description": "Represents a discount code applied to an order.",
                  "properties": {
                    "amount": {
                      "default": null,
                      "description": "The amount deducted from the order total.",
                      "nullable": true,
                      "title": "Amount",
                      "type": "string"
                    },
                    "code": {
                      "default": null,
                      "description": "The discount code.",
                      "nullable": true,
                      "title": "Code",
                      "type": "string"
                    },
                    "type": {
                      "default": null,
                      "description": "The type of discount.",
                      "nullable": true,
                      "title": "Type",
                      "type": "string"
                    }
                  },
                  "title": "DiscountCode",
                  "type": "object"
                },
                "nullable": true,
                "title": "Discount Codes",
                "type": "array"
              },
              "email": {
                "default": null,
                "description": "The customer's email address.",
                "nullable": true,
                "title": "Email",
                "type": "string"
              },
              "estimated_taxes": {
                "default": null,
                "description": "Whether taxes on the order are estimated.",
                "nullable": true,
                "title": "Estimated Taxes",
                "type": "boolean"
              },
              "financial_status": {
                "default": null,
                "description": "The payment status of the order. Valid values: pending, authorized, partially_paid, paid, partially_refunded, refunded, voided.",
                "nullable": true,
                "title": "Financial Status",
                "type": "string"
              },
              "fulfillment_status": {
                "default": null,
                "description": "The order's status in terms of fulfilled line items. Valid values: null (unfulfilled), fulfilled, partial, restocked.",
                "nullable": true,
                "title": "Fulfillment Status",
                "type": "string"
              },
              "fulfillments": {
                "default": null,
                "description": "Array of fulfillment records, each containing delivery information, tracking numbers, and line items.",
                "items": {
                  "description": "Represents a fulfillment record for an order.",
                  "properties": {
                    "admin_graphql_api_id": {
                      "default": null,
                      "description": "The GraphQL API identifier for the fulfillment.",
                      "nullable": true,
                      "title": "Admin Graphql Api Id",
                      "type": "string"
                    },
                    "created_at": {
                      "default": null,
                      "description": "The date and time when the fulfillment was created.",
                      "nullable": true,
                      "title": "Created At",
                      "type": "string"
                    },
                    "id": {
                      "default": null,
                      "description": "The unique identifier for the fulfillment.",
                      "nullable": true,
                      "title": "Id",
                      "type": "integer"
                    },
                    "line_items": {
                      "default": null,
                      "description": "Line items included in the fulfillment.",
                      "items": {
                        "description": "Represents a line item in an order.",
                        "properties": {
                          "admin_graphql_api_id": {
                            "default": null,
                            "description": "The GraphQL API identifier for the line item.",
                            "nullable": true,
                            "title": "Admin Graphql Api Id",
                            "type": "string"
                          },
                          "discount_allocations": {
                            "default": null,
                            "description": "Discount allocations applied to the line item.",
                            "items": {
                              "description": "Represents a discount allocation applied to a line item.",
                              "properties": {
                                "amount": {
                                  "default": null,
                                  "description": "The discount amount allocated to the line item.",
                                  "nullable": true,
                                  "title": "Amount",
                                  "type": "string"
                                },
                                "amount_set": {
                                  "additionalProperties": false,
                                  "default": null,
                                  "description": "Represents a price in both shop and presentment currencies.",
                                  "nullable": true,
                                  "properties": {
                                    "presentment_money": {
                                      "additionalProperties": false,
                                      "default": null,
                                      "description": "Represents a monetary amount with currency.",
                                      "nullable": true,
                                      "properties": {
                                        "amount": {
                                          "default": null,
                                          "description": "The amount in decimal format (e.g., '19.99').",
                                          "nullable": true,
                                          "title": "Amount",
                                          "type": "string"
                                        },
                                        "currency_code": {
                                          "default": null,
                                          "description": "The three-letter currency code (ISO 4217).",
                                          "nullable": true,
                                          "title": "Currency Code",
                                          "type": "string"
                                        }
                                      },
                                      "title": "Money",
                                      "type": "object"
                                    },
                                    "shop_money": {
                                      "additionalProperties": false,
                                      "default": null,
                                      "description": "Represents a monetary amount with currency.",
                                      "nullable": true,
                                      "properties": {
                                        "amount": {
                                          "default": null,
                                          "description": "The amount in decimal format (e.g., '19.99').",
                                          "nullable": true,
                                          "title": "Amount",
                                          "type": "string"
                                        },
                                        "currency_code": {
                                          "default": null,
                                          "description": "The three-letter currency code (ISO 4217).",
                                          "nullable": true,
                                          "title": "Currency Code",
                                          "type": "string"
                                        }
                                      },
                                      "title": "Money",
                                      "type": "object"
                                    }
                                  },
                                  "title": "MoneySet",
                                  "type": "object"
                                },
                                "discount_application_index": {
                                  "default": null,
                                  "description": "The index of the associated discount application in the order's discount_applications list.",
                                  "nullable": true,
                                  "title": "Discount Application Index",
                                  "type": "integer"
                                }
                              },
                              "title": "DiscountAllocation",
                              "type": "object"
                            },
                            "nullable": true,
                            "title": "Discount Allocations",
                            "type": "array"
                          },
                          "duties": {
                            "default": null,
                            "description": "List of duty objects applicable to the line item.",
                            "items": {
                              "additionalProperties": true,
                              "properties": {},
                              "type": "object"
                            },
                            "nullable": true,
                            "title": "Duties",
                            "type": "array"
                          },
                          "fulfillable_quantity": {
                            "default": null,
                            "description": "The amount available to fulfill, calculated as follows: quantity - max(refunded_quantity, fulfilled_quantity) - pending_fulfilled_quantity - open_fulfilled_quantity.",
                            "nullable": true,
                            "title": "Fulfillable Quantity",
                            "type": "integer"
                          },
                          "fulfillment_service": {
                            "default": null,
                            "description": "The fulfillment service for the variant. Returns 'manual' if none.",
                            "nullable": true,
                            "title": "Fulfillment Service",
                            "type": "string"
                          },
                          "fulfillment_status": {
                            "default": null,
                            "description": "The fulfillment status of the line item.",
                            "nullable": true,
                            "title": "Fulfillment Status",
                            "type": "string"
                          },
                          "gift_card": {
                            "default": null,
                            "description": "Whether the line item is a gift card.",
                            "nullable": true,
                            "title": "Gift Card",
                            "type": "boolean"
                          },
                          "grams": {
                            "default": null,
                            "description": "The weight of the line item in grams.",
                            "nullable": true,
                            "title": "Grams",
                            "type": "integer"
                          },
                          "id": {
                            "default": null,
                            "description": "The unique identifier for the line item.",
                            "nullable": true,
                            "title": "Id",
                            "type": "integer"
                          },
                          "name": {
                            "default": null,
                            "description": "The name of the product variant.",
                            "nullable": true,
                            "title": "Name",
                            "type": "string"
                          },
                          "price": {
                            "default": null,
                            "description": "The price of the line item including line-level discounts.",
                            "nullable": true,
                            "title": "Price",
                            "type": "string"
                          },
                          "price_set": {
                            "additionalProperties": false,
                            "default": null,
                            "description": "Represents a price in both shop and presentment currencies.",
                            "nullable": true,
                            "properties": {
                              "presentment_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              },
                              "shop_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              }
                            },
                            "title": "MoneySet",
                            "type": "object"
                          },
                          "product_exists": {
                            "default": null,
                            "description": "Whether the product exists.",
                            "nullable": true,
                            "title": "Product Exists",
                            "type": "boolean"
                          },
                          "product_id": {
                            "default": null,
                            "description": "The ID of the product. Can be null if the product was deleted.",
                            "nullable": true,
                            "title": "Product Id",
                            "type": "integer"
                          },
                          "properties": {
                            "default": null,
                            "description": "Custom properties for the line item (name-value pairs).",
                            "items": {
                              "additionalProperties": true,
                              "properties": {},
                              "type": "object"
                            },
                            "nullable": true,
                            "title": "Properties",
                            "type": "array"
                          },
                          "quantity": {
                            "default": null,
                            "description": "The quantity of the line item.",
                            "nullable": true,
                            "title": "Quantity",
                            "type": "integer"
                          },
                          "requires_shipping": {
                            "default": null,
                            "description": "Whether the line item requires shipping.",
                            "nullable": true,
                            "title": "Requires Shipping",
                            "type": "boolean"
                          },
                          "sku": {
                            "default": null,
                            "description": "The SKU of the variant.",
                            "nullable": true,
                            "title": "Sku",
                            "type": "string"
                          },
                          "tax_lines": {
                            "default": null,
                            "description": "Tax calculations applied to the line item.",
                            "items": {
                              "description": "Represents a tax line applied to an order or line item.",
                              "properties": {
                                "channel_liable": {
                                  "default": null,
                                  "description": "Whether the channel that submitted the tax line is liable for remitting.",
                                  "nullable": true,
                                  "title": "Channel Liable",
                                  "type": "boolean"
                                },
                                "price": {
                                  "default": null,
                                  "description": "The tax amount.",
                                  "nullable": true,
                                  "title": "Price",
                                  "type": "string"
                                },
                                "price_set": {
                                  "additionalProperties": false,
                                  "default": null,
                                  "description": "Represents a price in both shop and presentment currencies.",
                                  "nullable": true,
                                  "properties": {
                                    "presentment_money": {
                                      "additionalProperties": false,
                                      "default": null,
                                      "description": "Represents a monetary amount with currency.",
                                      "nullable": true,
                                      "properties": {
                                        "amount": {
                                          "default": null,
                                          "description": "The amount in decimal format (e.g., '19.99').",
                                          "nullable": true,
                                          "title": "Amount",
                                          "type": "string"
                                        },
                                        "currency_code": {
                                          "default": null,
                                          "description": "The three-letter currency code (ISO 4217).",
                                          "nullable": true,
                                          "title": "Currency Code",
                                          "type": "string"
                                        }
                                      },
                                      "title": "Money",
                                      "type": "object"
                                    },
                                    "shop_money": {
                                      "additionalProperties": false,
                                      "default": null,
                                      "description": "Represents a monetary amount with currency.",
                                      "nullable": true,
                                      "properties": {
                                        "amount": {
                                          "default": null,
                                          "description": "The amount in decimal format (e.g., '19.99').",
                                          "nullable": true,
                                          "title": "Amount",
                                          "type": "string"
                                        },
                                        "currency_code": {
                                          "default": null,
                                          "description": "The three-letter currency code (ISO 4217).",
                                          "nullable": true,
                                          "title": "Currency Code",
                                          "type": "string"
                                        }
                                      },
                                      "title": "Money",
                                      "type": "object"
                                    }
                                  },
                                  "title": "MoneySet",
                                  "type": "object"
                                },
                                "rate": {
                                  "default": null,
                                  "description": "The tax rate.",
                                  "nullable": true,
                                  "title": "Rate",
                                  "type": "number"
                                },
                                "title": {
                                  "default": null,
                                  "description": "The tax name.",
                                  "nullable": true,
                                  "title": "Title",
                                  "type": "string"
                                }
                              },
                              "title": "TaxLine",
                              "type": "object"
                            },
                            "nullable": true,
                            "title": "Tax Lines",
                            "type": "array"
                          },
                          "taxable": {
                            "default": null,
                            "description": "Whether the line item is taxable.",
                            "nullable": true,
                            "title": "Taxable",
                            "type": "boolean"
                          },
                          "title": {
                            "default": null,
                            "description": "The product title.",
                            "nullable": true,
                            "title": "Title",
                            "type": "string"
                          },
                          "total_discount": {
                            "default": null,
                            "description": "The total discount amount applied to this line item.",
                            "nullable": true,
                            "title": "Total Discount",
                            "type": "string"
                          },
                          "total_discount_set": {
                            "additionalProperties": false,
                            "default": null,
                            "description": "Represents a price in both shop and presentment currencies.",
                            "nullable": true,
                            "properties": {
                              "presentment_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              },
                              "shop_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              }
                            },
                            "title": "MoneySet",
                            "type": "object"
                          },
                          "variant_id": {
                            "default": null,
                            "description": "The ID of the specific product variant.",
                            "nullable": true,
                            "title": "Variant Id",
                            "type": "integer"
                          },
                          "variant_title": {
                            "default": null,
                            "description": "The title of the product variant.",
                            "nullable": true,
                            "title": "Variant Title",
                            "type": "string"
                          },
                          "vendor": {
                            "default": null,
                            "description": "The vendor of the product.",
                            "nullable": true,
                            "title": "Vendor",
                            "type": "string"
                          }
                        },
                        "title": "LineItem",
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Line Items",
                      "type": "array"
                    },
                    "location_id": {
                      "default": null,
                      "description": "The ID of the location from which the order was fulfilled.",
                      "nullable": true,
                      "title": "Location Id",
                      "type": "integer"
                    },
                    "name": {
                      "default": null,
                      "description": "The name of the fulfillment.",
                      "nullable": true,
                      "title": "Name",
                      "type": "string"
                    },
                    "order_id": {
                      "default": null,
                      "description": "The ID of the order that the fulfillment belongs to.",
                      "nullable": true,
                      "title": "Order Id",
                      "type": "integer"
                    },
                    "receipt": {
                      "additionalProperties": true,
                      "default": null,
                      "description": "The receipt for the fulfillment.",
                      "nullable": true,
                      "title": "Receipt",
                      "type": "object"
                    },
                    "service": {
                      "default": null,
                      "description": "The fulfillment service.",
                      "nullable": true,
                      "title": "Service",
                      "type": "string"
                    },
                    "shipment_status": {
                      "default": null,
                      "description": "The shipment status of the fulfillment.",
                      "nullable": true,
                      "title": "Shipment Status",
                      "type": "string"
                    },
                    "status": {
                      "default": null,
                      "description": "The fulfillment status.",
                      "nullable": true,
                      "title": "Status",
                      "type": "string"
                    },
                    "tracking_company": {
                      "default": null,
                      "description": "The name of the tracking company.",
                      "nullable": true,
                      "title": "Tracking Company",
                      "type": "string"
                    },
                    "tracking_number": {
                      "default": null,
                      "description": "The tracking number for the shipment.",
                      "nullable": true,
                      "title": "Tracking Number",
                      "type": "string"
                    },
                    "tracking_numbers": {
                      "default": null,
                      "description": "A list of tracking numbers for the shipment.",
                      "items": {
                        "properties": {},
                        "type": "string"
                      },
                      "nullable": true,
                      "title": "Tracking Numbers",
                      "type": "array"
                    },
                    "tracking_url": {
                      "default": null,
                      "description": "The URL to track the shipment.",
                      "nullable": true,
                      "title": "Tracking Url",
                      "type": "string"
                    },
                    "tracking_urls": {
                      "default": null,
                      "description": "A list of URLs to track the shipment.",
                      "items": {
                        "properties": {},
                        "type": "string"
                      },
                      "nullable": true,
                      "title": "Tracking Urls",
                      "type": "array"
                    },
                    "updated_at": {
                      "default": null,
                      "description": "The date and time when the fulfillment was last updated.",
                      "nullable": true,
                      "title": "Updated At",
                      "type": "string"
                    }
                  },
                  "title": "Fulfillment",
                  "type": "object"
                },
                "nullable": true,
                "title": "Fulfillments",
                "type": "array"
              },
              "gateway": {
                "default": null,
                "description": "The handleized name of the payment gateway used for the transaction.",
                "nullable": true,
                "title": "Gateway",
                "type": "string"
              },
              "id": {
                "default": null,
                "description": "The unique numeric identifier for the order.",
                "nullable": true,
                "title": "Id",
                "type": "integer"
              },
              "landing_site": {
                "default": null,
                "description": "The website landing page the customer arrived at before placing the order. Can be null.",
                "nullable": true,
                "title": "Landing Site",
                "type": "string"
              },
              "landing_site_ref": {
                "default": null,
                "description": "The landing site reference parameter.",
                "nullable": true,
                "title": "Landing Site Ref",
                "type": "string"
              },
              "line_items": {
                "default": null,
                "description": "Product items in order with pricing, tax details, fulfillment information, and custom properties.",
                "items": {
                  "description": "Represents a line item in an order.",
                  "properties": {
                    "admin_graphql_api_id": {
                      "default": null,
                      "description": "The GraphQL API identifier for the line item.",
                      "nullable": true,
                      "title": "Admin Graphql Api Id",
                      "type": "string"
                    },
                    "discount_allocations": {
                      "default": null,
                      "description": "Discount allocations applied to the line item.",
                      "items": {
                        "description": "Represents a discount allocation applied to a line item.",
                        "properties": {
                          "amount": {
                            "default": null,
                            "description": "The discount amount allocated to the line item.",
                            "nullable": true,
                            "title": "Amount",
                            "type": "string"
                          },
                          "amount_set": {
                            "additionalProperties": false,
                            "default": null,
                            "description": "Represents a price in both shop and presentment currencies.",
                            "nullable": true,
                            "properties": {
                              "presentment_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              },
                              "shop_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              }
                            },
                            "title": "MoneySet",
                            "type": "object"
                          },
                          "discount_application_index": {
                            "default": null,
                            "description": "The index of the associated discount application in the order's discount_applications list.",
                            "nullable": true,
                            "title": "Discount Application Index",
                            "type": "integer"
                          }
                        },
                        "title": "DiscountAllocation",
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Discount Allocations",
                      "type": "array"
                    },
                    "duties": {
                      "default": null,
                      "description": "List of duty objects applicable to the line item.",
                      "items": {
                        "additionalProperties": true,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Duties",
                      "type": "array"
                    },
                    "fulfillable_quantity": {
                      "default": null,
                      "description": "The amount available to fulfill, calculated as follows: quantity - max(refunded_quantity, fulfilled_quantity) - pending_fulfilled_quantity - open_fulfilled_quantity.",
                      "nullable": true,
                      "title": "Fulfillable Quantity",
                      "type": "integer"
                    },
                    "fulfillment_service": {
                      "default": null,
                      "description": "The fulfillment service for the variant. Returns 'manual' if none.",
                      "nullable": true,
                      "title": "Fulfillment Service",
                      "type": "string"
                    },
                    "fulfillment_status": {
                      "default": null,
                      "description": "The fulfillment status of the line item.",
                      "nullable": true,
                      "title": "Fulfillment Status",
                      "type": "string"
                    },
                    "gift_card": {
                      "default": null,
                      "description": "Whether the line item is a gift card.",
                      "nullable": true,
                      "title": "Gift Card",
                      "type": "boolean"
                    },
                    "grams": {
                      "default": null,
                      "description": "The weight of the line item in grams.",
                      "nullable": true,
                      "title": "Grams",
                      "type": "integer"
                    },
                    "id": {
                      "default": null,
                      "description": "The unique identifier for the line item.",
                      "nullable": true,
                      "title": "Id",
                      "type": "integer"
                    },
                    "name": {
                      "default": null,
                      "description": "The name of the product variant.",
                      "nullable": true,
                      "title": "Name",
                      "type": "string"
                    },
                    "price": {
                      "default": null,
                      "description": "The price of the line item including line-level discounts.",
                      "nullable": true,
                      "title": "Price",
                      "type": "string"
                    },
                    "price_set": {
                      "additionalProperties": false,
                      "default": null,
                      "description": "Represents a price in both shop and presentment currencies.",
                      "nullable": true,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "MoneySet",
                      "type": "object"
                    },
                    "product_exists": {
                      "default": null,
                      "description": "Whether the product exists.",
                      "nullable": true,
                      "title": "Product Exists",
                      "type": "boolean"
                    },
                    "product_id": {
                      "default": null,
                      "description": "The ID of the product. Can be null if the product was deleted.",
                      "nullable": true,
                      "title": "Product Id",
                      "type": "integer"
                    },
                    "properties": {
                      "default": null,
                      "description": "Custom properties for the line item (name-value pairs).",
                      "items": {
                        "additionalProperties": true,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Properties",
                      "type": "array"
                    },
                    "quantity": {
                      "default": null,
                      "description": "The quantity of the line item.",
                      "nullable": true,
                      "title": "Quantity",
                      "type": "integer"
                    },
                    "requires_shipping": {
                      "default": null,
                      "description": "Whether the line item requires shipping.",
                      "nullable": true,
                      "title": "Requires Shipping",
                      "type": "boolean"
                    },
                    "sku": {
                      "default": null,
                      "description": "The SKU of the variant.",
                      "nullable": true,
                      "title": "Sku",
                      "type": "string"
                    },
                    "tax_lines": {
                      "default": null,
                      "description": "Tax calculations applied to the line item.",
                      "items": {
                        "description": "Represents a tax line applied to an order or line item.",
                        "properties": {
                          "channel_liable": {
                            "default": null,
                            "description": "Whether the channel that submitted the tax line is liable for remitting.",
                            "nullable": true,
                            "title": "Channel Liable",
                            "type": "boolean"
                          },
                          "price": {
                            "default": null,
                            "description": "The tax amount.",
                            "nullable": true,
                            "title": "Price",
                            "type": "string"
                          },
                          "price_set": {
                            "additionalProperties": false,
                            "default": null,
                            "description": "Represents a price in both shop and presentment currencies.",
                            "nullable": true,
                            "properties": {
                              "presentment_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              },
                              "shop_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              }
                            },
                            "title": "MoneySet",
                            "type": "object"
                          },
                          "rate": {
                            "default": null,
                            "description": "The tax rate.",
                            "nullable": true,
                            "title": "Rate",
                            "type": "number"
                          },
                          "title": {
                            "default": null,
                            "description": "The tax name.",
                            "nullable": true,
                            "title": "Title",
                            "type": "string"
                          }
                        },
                        "title": "TaxLine",
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Tax Lines",
                      "type": "array"
                    },
                    "taxable": {
                      "default": null,
                      "description": "Whether the line item is taxable.",
                      "nullable": true,
                      "title": "Taxable",
                      "type": "boolean"
                    },
                    "title": {
                      "default": null,
                      "description": "The product title.",
                      "nullable": true,
                      "title": "Title",
                      "type": "string"
                    },
                    "total_discount": {
                      "default": null,
                      "description": "The total discount amount applied to this line item.",
                      "nullable": true,
                      "title": "Total Discount",
                      "type": "string"
                    },
                    "total_discount_set": {
                      "additionalProperties": false,
                      "default": null,
                      "description": "Represents a price in both shop and presentment currencies.",
                      "nullable": true,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "MoneySet",
                      "type": "object"
                    },
                    "variant_id": {
                      "default": null,
                      "description": "The ID of the specific product variant.",
                      "nullable": true,
                      "title": "Variant Id",
                      "type": "integer"
                    },
                    "variant_title": {
                      "default": null,
                      "description": "The title of the product variant.",
                      "nullable": true,
                      "title": "Variant Title",
                      "type": "string"
                    },
                    "vendor": {
                      "default": null,
                      "description": "The vendor of the product.",
                      "nullable": true,
                      "title": "Vendor",
                      "type": "string"
                    }
                  },
                  "title": "LineItem",
                  "type": "object"
                },
                "nullable": true,
                "title": "Line Items",
                "type": "array"
              },
              "location_id": {
                "default": null,
                "description": "The ID of the physical location where the order was placed, particularly relevant for POS orders.",
                "nullable": true,
                "title": "Location Id",
                "type": "integer"
              },
              "name": {
                "default": null,
                "description": "The order name, typically in the format '#1001'.",
                "nullable": true,
                "title": "Name",
                "type": "string"
              },
              "note": {
                "default": null,
                "description": "Additional information or instructions added by merchants or customers, commonly used for special delivery instructions, gift messages, or internal processing notes.",
                "nullable": true,
                "title": "Note",
                "type": "string"
              },
              "note_attributes": {
                "default": null,
                "description": "Additional data attached to the order, such as custom fields or calculated values.",
                "items": {
                  "description": "Represents a note attribute (custom field) on an order.",
                  "properties": {
                    "name": {
                      "default": null,
                      "description": "The attribute name.",
                      "nullable": true,
                      "title": "Name",
                      "type": "string"
                    },
                    "value": {
                      "default": null,
                      "description": "The attribute value.",
                      "nullable": true,
                      "title": "Value",
                      "type": "string"
                    }
                  },
                  "title": "NoteAttribute",
                  "type": "object"
                },
                "nullable": true,
                "title": "Note Attributes",
                "type": "array"
              },
              "number": {
                "default": null,
                "description": "The order number, a unique sequential number for the order.",
                "nullable": true,
                "title": "Number",
                "type": "integer"
              },
              "order_number": {
                "default": null,
                "description": "The order number used by the shop.",
                "nullable": true,
                "title": "Order Number",
                "type": "integer"
              },
              "order_status_url": {
                "default": null,
                "description": "The unique URL for the status page of the order, allowing customers to track order status.",
                "nullable": true,
                "title": "Order Status Url",
                "type": "string"
              },
              "original_total_additional_fees_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "original_total_duties_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "payment_details": {
                "additionalProperties": true,
                "default": null,
                "description": "Payment details including credit card information (masked) and payment method.",
                "nullable": true,
                "title": "Payment Details",
                "type": "object"
              },
              "payment_gateway_names": {
                "default": null,
                "description": "List of payment gateway names used for the order.",
                "items": {
                  "properties": {},
                  "type": "string"
                },
                "nullable": true,
                "title": "Payment Gateway Names",
                "type": "array"
              },
              "payment_terms": {
                "additionalProperties": true,
                "default": null,
                "description": "Payment terms information for the order.",
                "nullable": true,
                "title": "Payment Terms",
                "type": "object"
              },
              "phone": {
                "default": null,
                "description": "The customer's phone number for receiving SMS notifications.",
                "nullable": true,
                "title": "Phone",
                "type": "string"
              },
              "po_number": {
                "default": null,
                "description": "The purchase order number associated with the order.",
                "nullable": true,
                "title": "Po Number",
                "type": "string"
              },
              "presentment_currency": {
                "default": null,
                "description": "The currency code for the customer's local currency.",
                "nullable": true,
                "title": "Presentment Currency",
                "type": "string"
              },
              "processed_at": {
                "default": null,
                "description": "The date and time when the order was processed in ISO 8601 format.",
                "nullable": true,
                "title": "Processed At",
                "type": "string"
              },
              "processing_method": {
                "default": null,
                "description": "The payment processing method used.",
                "nullable": true,
                "title": "Processing Method",
                "type": "string"
              },
              "reference": {
                "default": null,
                "description": "A valid URL to the original order on the originating surface, displayed to merchants on the Order Details page.",
                "nullable": true,
                "title": "Reference",
                "type": "string"
              },
              "referring_site": {
                "default": null,
                "description": "The website or source that referred the customer to the store. Can be null.",
                "nullable": true,
                "title": "Referring Site",
                "type": "string"
              },
              "refunds": {
                "default": null,
                "description": "Array of refund transactions applied to the order.",
                "items": {
                  "description": "Represents a refund applied to an order.",
                  "properties": {
                    "admin_graphql_api_id": {
                      "default": null,
                      "description": "The GraphQL API identifier for the refund.",
                      "nullable": true,
                      "title": "Admin Graphql Api Id",
                      "type": "string"
                    },
                    "created_at": {
                      "default": null,
                      "description": "The date and time when the refund was created.",
                      "nullable": true,
                      "title": "Created At",
                      "type": "string"
                    },
                    "id": {
                      "default": null,
                      "description": "The unique identifier for the refund.",
                      "nullable": true,
                      "title": "Id",
                      "type": "integer"
                    },
                    "note": {
                      "default": null,
                      "description": "The reason for the refund.",
                      "nullable": true,
                      "title": "Note",
                      "type": "string"
                    },
                    "order_adjustments": {
                      "default": null,
                      "description": "A list of order-level adjustments to the refund.",
                      "items": {
                        "additionalProperties": true,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Order Adjustments",
                      "type": "array"
                    },
                    "order_id": {
                      "default": null,
                      "description": "The ID of the order that the refund belongs to.",
                      "nullable": true,
                      "title": "Order Id",
                      "type": "integer"
                    },
                    "processed_at": {
                      "default": null,
                      "description": "The date and time when the refund was processed.",
                      "nullable": true,
                      "title": "Processed At",
                      "type": "string"
                    },
                    "refund_line_items": {
                      "default": null,
                      "description": "The list of refund line items.",
                      "items": {
                        "additionalProperties": true,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Refund Line Items",
                      "type": "array"
                    },
                    "restock": {
                      "default": null,
                      "description": "Whether to restock the items.",
                      "nullable": true,
                      "title": "Restock",
                      "type": "boolean"
                    },
                    "transactions": {
                      "default": null,
                      "description": "The list of transactions associated with the refund.",
                      "items": {
                        "additionalProperties": true,
                        "properties": {},
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Transactions",
                      "type": "array"
                    },
                    "user_id": {
                      "default": null,
                      "description": "The ID of the user who performed the refund.",
                      "nullable": true,
                      "title": "User Id",
                      "type": "integer"
                    }
                  },
                  "title": "Refund",
                  "type": "object"
                },
                "nullable": true,
                "title": "Refunds",
                "type": "array"
              },
              "shipping_address": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a mailing address.",
                "nullable": true,
                "properties": {
                  "address1": {
                    "default": null,
                    "description": "Street address line 1.",
                    "nullable": true,
                    "title": "Address1",
                    "type": "string"
                  },
                  "address2": {
                    "default": null,
                    "description": "Street address line 2.",
                    "nullable": true,
                    "title": "Address2",
                    "type": "string"
                  },
                  "city": {
                    "default": null,
                    "description": "City name.",
                    "nullable": true,
                    "title": "City",
                    "type": "string"
                  },
                  "company": {
                    "default": null,
                    "description": "Company name.",
                    "nullable": true,
                    "title": "Company",
                    "type": "string"
                  },
                  "country": {
                    "default": null,
                    "description": "Country name.",
                    "nullable": true,
                    "title": "Country",
                    "type": "string"
                  },
                  "country_code": {
                    "default": null,
                    "description": "Two-letter country code.",
                    "nullable": true,
                    "title": "Country Code",
                    "type": "string"
                  },
                  "first_name": {
                    "default": null,
                    "description": "First name.",
                    "nullable": true,
                    "title": "First Name",
                    "type": "string"
                  },
                  "last_name": {
                    "default": null,
                    "description": "Last name.",
                    "nullable": true,
                    "title": "Last Name",
                    "type": "string"
                  },
                  "latitude": {
                    "default": null,
                    "description": "Latitude coordinate.",
                    "nullable": true,
                    "title": "Latitude",
                    "type": "number"
                  },
                  "longitude": {
                    "default": null,
                    "description": "Longitude coordinate.",
                    "nullable": true,
                    "title": "Longitude",
                    "type": "number"
                  },
                  "name": {
                    "default": null,
                    "description": "Full name.",
                    "nullable": true,
                    "title": "Name",
                    "type": "string"
                  },
                  "phone": {
                    "default": null,
                    "description": "Phone number.",
                    "nullable": true,
                    "title": "Phone",
                    "type": "string"
                  },
                  "province": {
                    "default": null,
                    "description": "Province or state name.",
                    "nullable": true,
                    "title": "Province",
                    "type": "string"
                  },
                  "province_code": {
                    "default": null,
                    "description": "Province or state code.",
                    "nullable": true,
                    "title": "Province Code",
                    "type": "string"
                  },
                  "zip": {
                    "default": null,
                    "description": "Postal or ZIP code.",
                    "nullable": true,
                    "title": "Zip",
                    "type": "string"
                  }
                },
                "title": "Address",
                "type": "object"
              },
              "shipping_lines": {
                "default": null,
                "description": "A summary of all shipping costs on the order, aggregating shipping charges, discounts, and taxes.",
                "items": {
                  "description": "Represents a shipping line in an order.",
                  "properties": {
                    "carrier_identifier": {
                      "default": null,
                      "description": "The carrier identifier.",
                      "nullable": true,
                      "title": "Carrier Identifier",
                      "type": "string"
                    },
                    "code": {
                      "default": null,
                      "description": "The shipping method code.",
                      "nullable": true,
                      "title": "Code",
                      "type": "string"
                    },
                    "delivery_category": {
                      "default": null,
                      "description": "The delivery category.",
                      "nullable": true,
                      "title": "Delivery Category",
                      "type": "string"
                    },
                    "discount_allocations": {
                      "default": null,
                      "description": "Discount allocations applied to the shipping line.",
                      "items": {
                        "description": "Represents a discount allocation applied to a line item.",
                        "properties": {
                          "amount": {
                            "default": null,
                            "description": "The discount amount allocated to the line item.",
                            "nullable": true,
                            "title": "Amount",
                            "type": "string"
                          },
                          "amount_set": {
                            "additionalProperties": false,
                            "default": null,
                            "description": "Represents a price in both shop and presentment currencies.",
                            "nullable": true,
                            "properties": {
                              "presentment_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              },
                              "shop_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              }
                            },
                            "title": "MoneySet",
                            "type": "object"
                          },
                          "discount_application_index": {
                            "default": null,
                            "description": "The index of the associated discount application in the order's discount_applications list.",
                            "nullable": true,
                            "title": "Discount Application Index",
                            "type": "integer"
                          }
                        },
                        "title": "DiscountAllocation",
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Discount Allocations",
                      "type": "array"
                    },
                    "discounted_price": {
                      "default": null,
                      "description": "The discounted price of the shipping line.",
                      "nullable": true,
                      "title": "Discounted Price",
                      "type": "string"
                    },
                    "discounted_price_set": {
                      "additionalProperties": false,
                      "default": null,
                      "description": "Represents a price in both shop and presentment currencies.",
                      "nullable": true,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "MoneySet",
                      "type": "object"
                    },
                    "id": {
                      "default": null,
                      "description": "The unique identifier for the shipping line.",
                      "nullable": true,
                      "title": "Id",
                      "type": "integer"
                    },
                    "phone": {
                      "default": null,
                      "description": "The phone number for the shipping address.",
                      "nullable": true,
                      "title": "Phone",
                      "type": "string"
                    },
                    "price": {
                      "default": null,
                      "description": "The shipping price.",
                      "nullable": true,
                      "title": "Price",
                      "type": "string"
                    },
                    "price_set": {
                      "additionalProperties": false,
                      "default": null,
                      "description": "Represents a price in both shop and presentment currencies.",
                      "nullable": true,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "MoneySet",
                      "type": "object"
                    },
                    "requested_fulfillment_service_id": {
                      "default": null,
                      "description": "The requested fulfillment service ID.",
                      "nullable": true,
                      "title": "Requested Fulfillment Service Id",
                      "type": "string"
                    },
                    "source": {
                      "default": null,
                      "description": "The source of the shipping line.",
                      "nullable": true,
                      "title": "Source",
                      "type": "string"
                    },
                    "tax_lines": {
                      "default": null,
                      "description": "Tax calculations applied to the shipping line.",
                      "items": {
                        "description": "Represents a tax line applied to an order or line item.",
                        "properties": {
                          "channel_liable": {
                            "default": null,
                            "description": "Whether the channel that submitted the tax line is liable for remitting.",
                            "nullable": true,
                            "title": "Channel Liable",
                            "type": "boolean"
                          },
                          "price": {
                            "default": null,
                            "description": "The tax amount.",
                            "nullable": true,
                            "title": "Price",
                            "type": "string"
                          },
                          "price_set": {
                            "additionalProperties": false,
                            "default": null,
                            "description": "Represents a price in both shop and presentment currencies.",
                            "nullable": true,
                            "properties": {
                              "presentment_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              },
                              "shop_money": {
                                "additionalProperties": false,
                                "default": null,
                                "description": "Represents a monetary amount with currency.",
                                "nullable": true,
                                "properties": {
                                  "amount": {
                                    "default": null,
                                    "description": "The amount in decimal format (e.g., '19.99').",
                                    "nullable": true,
                                    "title": "Amount",
                                    "type": "string"
                                  },
                                  "currency_code": {
                                    "default": null,
                                    "description": "The three-letter currency code (ISO 4217).",
                                    "nullable": true,
                                    "title": "Currency Code",
                                    "type": "string"
                                  }
                                },
                                "title": "Money",
                                "type": "object"
                              }
                            },
                            "title": "MoneySet",
                            "type": "object"
                          },
                          "rate": {
                            "default": null,
                            "description": "The tax rate.",
                            "nullable": true,
                            "title": "Rate",
                            "type": "number"
                          },
                          "title": {
                            "default": null,
                            "description": "The tax name.",
                            "nullable": true,
                            "title": "Title",
                            "type": "string"
                          }
                        },
                        "title": "TaxLine",
                        "type": "object"
                      },
                      "nullable": true,
                      "title": "Tax Lines",
                      "type": "array"
                    },
                    "title": {
                      "default": null,
                      "description": "The shipping method title.",
                      "nullable": true,
                      "title": "Title",
                      "type": "string"
                    }
                  },
                  "title": "ShippingLine",
                  "type": "object"
                },
                "nullable": true,
                "title": "Shipping Lines",
                "type": "array"
              },
              "source_identifier": {
                "default": null,
                "description": "Source identifier field (unsupported and subject to change without notice).",
                "nullable": true,
                "title": "Source Identifier",
                "type": "string"
              },
              "source_name": {
                "default": null,
                "description": "The source of the order (e.g., 'web', 'pos', 'api').",
                "nullable": true,
                "title": "Source Name",
                "type": "string"
              },
              "source_url": {
                "default": null,
                "description": "The URL where the order originated.",
                "nullable": true,
                "title": "Source Url",
                "type": "string"
              },
              "subtotal_price": {
                "default": null,
                "description": "The total price of the line items in the order before taxes and shipping.",
                "nullable": true,
                "title": "Subtotal Price",
                "type": "string"
              },
              "subtotal_price_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "tags": {
                "default": null,
                "description": "A comma-separated list of tags that have been added to the order.",
                "nullable": true,
                "title": "Tags",
                "type": "string"
              },
              "tax_lines": {
                "default": null,
                "description": "Tax calculations applied at the order level, including duties and import fees.",
                "items": {
                  "description": "Represents a tax line applied to an order or line item.",
                  "properties": {
                    "channel_liable": {
                      "default": null,
                      "description": "Whether the channel that submitted the tax line is liable for remitting.",
                      "nullable": true,
                      "title": "Channel Liable",
                      "type": "boolean"
                    },
                    "price": {
                      "default": null,
                      "description": "The tax amount.",
                      "nullable": true,
                      "title": "Price",
                      "type": "string"
                    },
                    "price_set": {
                      "additionalProperties": false,
                      "default": null,
                      "description": "Represents a price in both shop and presentment currencies.",
                      "nullable": true,
                      "properties": {
                        "presentment_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        },
                        "shop_money": {
                          "additionalProperties": false,
                          "default": null,
                          "description": "Represents a monetary amount with currency.",
                          "nullable": true,
                          "properties": {
                            "amount": {
                              "default": null,
                              "description": "The amount in decimal format (e.g., '19.99').",
                              "nullable": true,
                              "title": "Amount",
                              "type": "string"
                            },
                            "currency_code": {
                              "default": null,
                              "description": "The three-letter currency code (ISO 4217).",
                              "nullable": true,
                              "title": "Currency Code",
                              "type": "string"
                            }
                          },
                          "title": "Money",
                          "type": "object"
                        }
                      },
                      "title": "MoneySet",
                      "type": "object"
                    },
                    "rate": {
                      "default": null,
                      "description": "The tax rate.",
                      "nullable": true,
                      "title": "Rate",
                      "type": "number"
                    },
                    "title": {
                      "default": null,
                      "description": "The tax name.",
                      "nullable": true,
                      "title": "Title",
                      "type": "string"
                    }
                  },
                  "title": "TaxLine",
                  "type": "object"
                },
                "nullable": true,
                "title": "Tax Lines",
                "type": "array"
              },
              "taxes_included": {
                "default": null,
                "description": "Whether taxes are included in the prices.",
                "nullable": true,
                "title": "Taxes Included",
                "type": "boolean"
              },
              "test": {
                "default": null,
                "description": "Whether this is a test order.",
                "nullable": true,
                "title": "Test",
                "type": "boolean"
              },
              "token": {
                "default": null,
                "description": "The unique token for the order.",
                "nullable": true,
                "title": "Token",
                "type": "string"
              },
              "total_discounts": {
                "default": null,
                "description": "The total amount of discounts applied to the order.",
                "nullable": true,
                "title": "Total Discounts",
                "type": "string"
              },
              "total_discounts_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "total_line_items_price": {
                "default": null,
                "description": "The sum of all line item prices before discounts, taxes, and shipping.",
                "nullable": true,
                "title": "Total Line Items Price",
                "type": "string"
              },
              "total_line_items_price_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "total_outstanding": {
                "default": null,
                "description": "The outstanding amount remaining on the order.",
                "nullable": true,
                "title": "Total Outstanding",
                "type": "string"
              },
              "total_price": {
                "default": null,
                "description": "The total price of the order including taxes and shipping.",
                "nullable": true,
                "title": "Total Price",
                "type": "string"
              },
              "total_price_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "total_price_usd": {
                "default": null,
                "description": "The total price of the order in USD.",
                "nullable": true,
                "title": "Total Price Usd",
                "type": "string"
              },
              "total_shipping_price_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "total_tax": {
                "default": null,
                "description": "The sum of all taxes applied to the order.",
                "nullable": true,
                "title": "Total Tax",
                "type": "string"
              },
              "total_tax_set": {
                "additionalProperties": false,
                "default": null,
                "description": "Represents a price in both shop and presentment currencies.",
                "nullable": true,
                "properties": {
                  "presentment_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  },
                  "shop_money": {
                    "additionalProperties": false,
                    "default": null,
                    "description": "Represents a monetary amount with currency.",
                    "nullable": true,
                    "properties": {
                      "amount": {
                        "default": null,
                        "description": "The amount in decimal format (e.g., '19.99').",
                        "nullable": true,
                        "title": "Amount",
                        "type": "string"
                      },
                      "currency_code": {
                        "default": null,
                        "description": "The three-letter currency code (ISO 4217).",
                        "nullable": true,
                        "title": "Currency Code",
                        "type": "string"
                      }
                    },
                    "title": "Money",
                    "type": "object"
                  }
                },
                "title": "MoneySet",
                "type": "object"
              },
              "total_tip_received": {
                "default": null,
                "description": "The sum of all tip amounts received for the order.",
                "nullable": true,
                "title": "Total Tip Received",
                "type": "string"
              },
              "total_weight": {
                "default": null,
                "description": "The total weight of the order in grams. Returns 0 when there is no weight.",
                "nullable": true,
                "title": "Total Weight",
                "type": "integer"
              },
              "updated_at": {
                "default": null,
                "description": "The date and time when the order was last updated in ISO 8601 format.",
                "nullable": true,
                "title": "Updated At",
                "type": "string"
              },
              "user_id": {
                "default": null,
                "description": "The ID of the user who created the order.",
                "nullable": true,
                "title": "User Id",
                "type": "integer"
              }
            },
            "title": "Order",
            "type": "object"
          },
          "title": "Orders",
          "type": "array"
        }
      },
      "required": [
        "orders"
      ],
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": null,
      "description": "Error if any occurred during the execution of the action",
      "nullable": true,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "GetOrderListResponseWrapper",
  "type": "object"
}"""
)

SHOPIFY_GET_CUSTOMER_OUTPUT_SCHEMA = json.loads(
  """{
  "properties": {
    "data": {
      "additionalProperties": false,
      "description": "Data from the action execution",
      "properties": {
        "customer": {
          "additionalProperties": false,
          "description": "The customer resource containing all customer information",
          "properties": {
            "addresses": {
              "description": "A list of the ten most recently updated addresses for the customer",
              "items": {
                "description": "Customer address information.",
                "properties": {
                  "address1": {
                    "description": "The customer's mailing address",
                    "title": "Address1",
                    "type": "string"
                  },
                  "address2": {
                    "default": null,
                    "description": "An additional field for the customer's mailing address",
                    "nullable": true,
                    "title": "Address2",
                    "type": "string"
                  },
                  "city": {
                    "description": "The customer's city, town, or village",
                    "title": "City",
                    "type": "string"
                  },
                  "company": {
                    "default": null,
                    "description": "The customer's company name",
                    "nullable": true,
                    "title": "Company",
                    "type": "string"
                  },
                  "country": {
                    "description": "The customer's country",
                    "title": "Country",
                    "type": "string"
                  },
                  "country_code": {
                    "description": "The two-letter country code corresponding to the country",
                    "title": "Country Code",
                    "type": "string"
                  },
                  "country_name": {
                    "description": "The full name of the country",
                    "title": "Country Name",
                    "type": "string"
                  },
                  "customer_id": {
                    "description": "The ID of the customer that the address belongs to",
                    "title": "Customer Id",
                    "type": "integer"
                  },
                  "default": {
                    "description": "Whether this address is the default address for the customer",
                    "title": "Default",
                    "type": "boolean"
                  },
                  "first_name": {
                    "default": null,
                    "description": "The customer's first name",
                    "nullable": true,
                    "title": "First Name",
                    "type": "string"
                  },
                  "id": {
                    "description": "Unique identifier for the address",
                    "title": "Id",
                    "type": "integer"
                  },
                  "last_name": {
                    "default": null,
                    "description": "The customer's last name",
                    "nullable": true,
                    "title": "Last Name",
                    "type": "string"
                  },
                  "name": {
                    "default": null,
                    "description": "The customer's name",
                    "nullable": true,
                    "title": "Name",
                    "type": "string"
                  },
                  "phone": {
                    "default": null,
                    "description": "The customer's phone number at this address",
                    "nullable": true,
                    "title": "Phone",
                    "type": "string"
                  },
                  "province": {
                    "default": null,
                    "description": "The customer's region name (province, state, prefecture, etc.)",
                    "nullable": true,
                    "title": "Province",
                    "type": "string"
                  },
                  "province_code": {
                    "default": null,
                    "description": "The code for the region of the address",
                    "nullable": true,
                    "title": "Province Code",
                    "type": "string"
                  },
                  "zip": {
                    "description": "The customer's postal code or zip code",
                    "title": "Zip",
                    "type": "string"
                  }
                },
                "required": [
                  "id",
                  "customer_id",
                  "address1",
                  "city",
                  "country",
                  "zip",
                  "country_code",
                  "country_name",
                  "default"
                ],
                "title": "Address",
                "type": "object"
              },
              "title": "Addresses",
              "type": "array"
            },
            "admin_graphql_api_id": {
              "description": "The GraphQL GID for the customer resource",
              "title": "Admin Graphql Api Id",
              "type": "string"
            },
            "created_at": {
              "description": "The date and time (ISO 8601 format) when the customer was created",
              "title": "Created At",
              "type": "string"
            },
            "currency": {
              "description": "The three-letter code (ISO 4217 format) for the currency that the customer used when they paid for their last order (deprecated field)",
              "title": "Currency",
              "type": "string"
            },
            "default_address": {
              "additionalProperties": false,
              "default": null,
              "description": "Customer address information.",
              "nullable": true,
              "properties": {
                "address1": {
                  "description": "The customer's mailing address",
                  "title": "Address1",
                  "type": "string"
                },
                "address2": {
                  "default": null,
                  "description": "An additional field for the customer's mailing address",
                  "nullable": true,
                  "title": "Address2",
                  "type": "string"
                },
                "city": {
                  "description": "The customer's city, town, or village",
                  "title": "City",
                  "type": "string"
                },
                "company": {
                  "default": null,
                  "description": "The customer's company name",
                  "nullable": true,
                  "title": "Company",
                  "type": "string"
                },
                "country": {
                  "description": "The customer's country",
                  "title": "Country",
                  "type": "string"
                },
                "country_code": {
                  "description": "The two-letter country code corresponding to the country",
                  "title": "Country Code",
                  "type": "string"
                },
                "country_name": {
                  "description": "The full name of the country",
                  "title": "Country Name",
                  "type": "string"
                },
                "customer_id": {
                  "description": "The ID of the customer that the address belongs to",
                  "title": "Customer Id",
                  "type": "integer"
                },
                "default": {
                  "description": "Whether this address is the default address for the customer",
                  "title": "Default",
                  "type": "boolean"
                },
                "first_name": {
                  "default": null,
                  "description": "The customer's first name",
                  "nullable": true,
                  "title": "First Name",
                  "type": "string"
                },
                "id": {
                  "description": "Unique identifier for the address",
                  "title": "Id",
                  "type": "integer"
                },
                "last_name": {
                  "default": null,
                  "description": "The customer's last name",
                  "nullable": true,
                  "title": "Last Name",
                  "type": "string"
                },
                "name": {
                  "default": null,
                  "description": "The customer's name",
                  "nullable": true,
                  "title": "Name",
                  "type": "string"
                },
                "phone": {
                  "default": null,
                  "description": "The customer's phone number at this address",
                  "nullable": true,
                  "title": "Phone",
                  "type": "string"
                },
                "province": {
                  "default": null,
                  "description": "The customer's region name (province, state, prefecture, etc.)",
                  "nullable": true,
                  "title": "Province",
                  "type": "string"
                },
                "province_code": {
                  "default": null,
                  "description": "The code for the region of the address",
                  "nullable": true,
                  "title": "Province Code",
                  "type": "string"
                },
                "zip": {
                  "description": "The customer's postal code or zip code",
                  "title": "Zip",
                  "type": "string"
                }
              },
              "required": [
                "id",
                "customer_id",
                "address1",
                "city",
                "country",
                "zip",
                "country_code",
                "country_name",
                "default"
              ],
              "title": "Address",
              "type": "object"
            },
            "email": {
              "description": "The unique email address of the customer",
              "title": "Email",
              "type": "string"
            },
            "email_marketing_consent": {
              "additionalProperties": false,
              "default": null,
              "description": "Email marketing consent information.",
              "nullable": true,
              "properties": {
                "consent_updated_at": {
                  "default": null,
                  "description": "The date and time (ISO 8601 format) when the customer consented or objected to receiving marketing material by email",
                  "nullable": true,
                  "title": "Consent Updated At",
                  "type": "string"
                },
                "opt_in_level": {
                  "default": null,
                  "description": "The marketing subscription opt-in level. Valid values: single_opt_in, confirmed_opt_in, unknown",
                  "nullable": true,
                  "title": "Opt In Level",
                  "type": "string"
                },
                "state": {
                  "description": "The current email marketing state. Valid values: not_subscribed, subscribed, invalid, pending",
                  "title": "State",
                  "type": "string"
                }
              },
              "required": [
                "state"
              ],
              "title": "EmailMarketingConsent",
              "type": "object"
            },
            "first_name": {
              "default": null,
              "description": "Customer's given name",
              "nullable": true,
              "title": "First Name",
              "type": "string"
            },
            "id": {
              "description": "Unique identifier for the customer",
              "title": "Id",
              "type": "integer"
            },
            "last_name": {
              "default": null,
              "description": "Customer's family name",
              "nullable": true,
              "title": "Last Name",
              "type": "string"
            },
            "last_order_id": {
              "default": null,
              "description": "The ID of the customer's last order",
              "nullable": true,
              "title": "Last Order Id",
              "type": "integer"
            },
            "last_order_name": {
              "default": null,
              "description": "The name of the customer's last order (e.g., #1001)",
              "nullable": true,
              "title": "Last Order Name",
              "type": "string"
            },
            "multipass_identifier": {
              "default": null,
              "description": "A unique identifier used in Shopify Multipass login (legacy field)",
              "nullable": true,
              "title": "Multipass Identifier",
              "type": "string"
            },
            "note": {
              "default": null,
              "description": "A note about the customer for internal use by the merchant",
              "nullable": true,
              "title": "Note",
              "type": "string"
            },
            "orders_count": {
              "description": "The total number of orders associated with this customer",
              "title": "Orders Count",
              "type": "integer"
            },
            "phone": {
              "default": null,
              "description": "Customer's phone number in E.164 format",
              "nullable": true,
              "title": "Phone",
              "type": "string"
            },
            "sms_marketing_consent": {
              "additionalProperties": false,
              "default": null,
              "description": "SMS marketing consent information.",
              "nullable": true,
              "properties": {
                "consent_collected_from": {
                  "default": null,
                  "description": "The source from which consent information was collected. Valid values: SHOPIFY, OTHER",
                  "nullable": true,
                  "title": "Consent Collected From",
                  "type": "string"
                },
                "consent_updated_at": {
                  "default": null,
                  "description": "The date and time (ISO 8601 format) when the customer consented or objected to receiving marketing material by SMS",
                  "nullable": true,
                  "title": "Consent Updated At",
                  "type": "string"
                },
                "opt_in_level": {
                  "description": "The marketing subscription opt-in level. Valid values: single_opt_in, confirmed_opt_in, unknown",
                  "title": "Opt In Level",
                  "type": "string"
                },
                "state": {
                  "description": "The current SMS marketing state. Valid values: not_subscribed, subscribed, pending",
                  "title": "State",
                  "type": "string"
                }
              },
              "required": [
                "state",
                "opt_in_level"
              ],
              "title": "SmsMarketingConsent",
              "type": "object"
            },
            "state": {
              "description": "The state of the customer account. Valid values: enabled, disabled",
              "title": "State",
              "type": "string"
            },
            "tags": {
              "default": null,
              "description": "Tags that the shop owner has attached to the customer, formatted as a string of comma-separated values",
              "nullable": true,
              "title": "Tags",
              "type": "string"
            },
            "tax_exempt": {
              "description": "Whether the customer is exempt from paying taxes on their order",
              "title": "Tax Exempt",
              "type": "boolean"
            },
            "tax_exemptions": {
              "description": "The list of tax exemptions applied to the customer",
              "items": {
                "properties": {},
                "type": "string"
              },
              "title": "Tax Exemptions",
              "type": "array"
            },
            "total_spent": {
              "description": "The total amount of money that the customer has spent across all their orders",
              "title": "Total Spent",
              "type": "string"
            },
            "updated_at": {
              "description": "The date and time (ISO 8601 format) when the customer was last updated",
              "title": "Updated At",
              "type": "string"
            },
            "verified_email": {
              "description": "Whether the customer has verified their email address",
              "title": "Verified Email",
              "type": "boolean"
            }
          },
          "required": [
            "id",
            "email",
            "created_at",
            "updated_at",
            "verified_email",
            "state",
            "orders_count",
            "total_spent",
            "tax_exempt",
            "tax_exemptions",
            "currency",
            "addresses",
            "admin_graphql_api_id"
          ],
          "title": "Customer",
          "type": "object"
        }
      },
      "required": [
        "customer"
      ],
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": null,
      "description": "Error if any occurred during the execution of the action",
      "nullable": true,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "GetCustomerResponseWrapper",
  "type": "object"
}"""
)

shopify_get_order_list_output_schema = SHOPIFY_GET_ORDER_LIST_OUTPUT_SCHEMA
shopify_get_ordersby_id_output_schema = SHOPIFY_GET_ORDERSBY_ID_OUTPUT_SCHEMA
shopify_update_order_output_schema = SHOPIFY_UPDATE_ORDER_OUTPUT_SCHEMA
shopify_get_customer_output_schema = SHOPIFY_GET_CUSTOMER_OUTPUT_SCHEMA
