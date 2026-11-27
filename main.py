import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("chrome-extension://"):
        # Chrome launches this same executable with its origin as argv[1].
        # Keep native messaging free of GUI startup and credential access.
        from buzz.browser_integration.host import main
        sys.exit(main())
    else:
        import buzz.buzz
        buzz.buzz.main()
