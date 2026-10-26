//! metallib-pack OUT.metallib STAGE:NAME:FILE.air [...]: a .metallib of hand-written AIR modules, one per
//! function, in the layout Apple's toolchain writes (metal2vulkan-devtools' writer, which metal2vulkan's own
//! tests use), then read back with metal2vulkan's parser. STAGE is vertex, fragment or kernel. For the probes
//! that want a metallib where no Apple metal compiler is installed (layerprobe).

use metal2vulkan_air::container::{self, Library};
use metal2vulkan_devtools::metallib::{metallib, wrap, MtlbFunction};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: metallib-pack OUT.metallib STAGE:NAME:FILE.air [...]");
        std::process::exit(2);
    }
    let mut owned = Vec::new();
    for spec in &args[2..] {
        let mut parts = spec.splitn(3, ':');
        let (stage, name, file) = (parts.next().unwrap(), parts.next().unwrap_or(""), parts.next().unwrap_or(""));
        let type_code = match stage {
            "vertex" => 0u8,
            "fragment" => 1,
            "kernel" => 2,
            _ => panic!("stage {stage}: vertex, fragment or kernel"),
        };
        let air = std::fs::read(file).unwrap_or_else(|e| panic!("{file}: {e}"));
        owned.push((name.to_string(), type_code, wrap(&air)));
    }
    let functions: Vec<MtlbFunction<'_>> = owned
        .iter()
        .map(|(name, type_code, bitcode)| MtlbFunction {
            name,
            type_code: *type_code,
            bitcode: bitcode.clone(),
            constants: vec![],
            public: vec![],
            tags: vec![],
        })
        .collect();
    let bytes = metallib(&functions);
    match container::parse(&bytes).expect("metal2vulkan cannot parse the metallib") {
        Library::Metallib(lib) => {
            for f in &lib.functions {
                println!("{}: {:?}, AIR {:?}, Metal {:?}, {} bytes of bitcode", f.name, f.stage, f.air_version,
                    f.language_version, f.bitcode.len());
            }
        }
        Library::Module(_) => panic!("not a metallib"),
    }
    std::fs::write(&args[1], &bytes).unwrap();
    println!("{}: {} bytes", args[1], bytes.len());
}
