; layerprobe.metal's bg_vs by hand (no Apple compiler here): V { float4 pos [[position]]; float4 color; float2 uv; },
; pos = data[vid * 2], color = data[vid * 2 + 1], uv = pos.xy * 0.5 + 0.5. Metadata in the form of metal2vulkan's
; runtime_examples.ll fixture (Apple metalfe output).
target datalayout = "e-p:64:64:64-i1:8:8-i8:8:8-i16:16:16-i32:32:32-i64:64:64-f32:32:32-f64:64:64-v16:16:16-v24:32:32-v32:32:32-v48:64:64-v64:64:64-v96:128:128-v128:128:128-v192:256:256-v256:256:256-v512:512:512-v1024:1024:1024-n8:16:32"
target triple = "air64_v28-apple-macosx26.0.0"

define <{ <4 x float>, <4 x float>, <2 x float> }> @bg_vs(i32 noundef %0, ptr addrspace(1) noundef readonly "air-buffer-no-alias" %1) local_unnamed_addr #0 {
  %3 = zext i32 %0 to i64
  %4 = shl nuw nsw i64 %3, 1
  %5 = getelementptr inbounds <4 x float>, ptr addrspace(1) %1, i64 %4
  %6 = load <4 x float>, ptr addrspace(1) %5, align 16
  %7 = or disjoint i64 %4, 1
  %8 = getelementptr inbounds <4 x float>, ptr addrspace(1) %1, i64 %7
  %9 = load <4 x float>, ptr addrspace(1) %8, align 16
  %10 = shufflevector <4 x float> %6, <4 x float> poison, <2 x i32> <i32 0, i32 1>
  %11 = fmul fast <2 x float> %10, <float 5.000000e-01, float 5.000000e-01>
  %12 = fadd fast <2 x float> %11, <float 5.000000e-01, float 5.000000e-01>
  %13 = insertvalue <{ <4 x float>, <4 x float>, <2 x float> }> undef, <4 x float> %6, 0
  %14 = insertvalue <{ <4 x float>, <4 x float>, <2 x float> }> %13, <4 x float> %9, 1
  %15 = insertvalue <{ <4 x float>, <4 x float>, <2 x float> }> %14, <2 x float> %12, 2
  ret <{ <4 x float>, <4 x float>, <2 x float> }> %15
}

attributes #0 = { mustprogress nofree norecurse nosync nounwind willreturn memory(argmem: read) }

!llvm.module.flags = !{!0, !1, !2, !3, !4, !5, !6, !7, !8}
!air.compile_options = !{!20, !21}
!llvm.ident = !{!22}
!air.version = !{!23}
!air.language_version = !{!24}

!0 = !{i32 2, !"SDK Version", [2 x i32] [i32 27, i32 0]}
!1 = !{i32 1, !"wchar_size", i32 4}
!2 = !{i32 7, !"frame-pointer", i32 2}
!3 = !{i32 7, !"air.max_device_buffers", i32 31}
!4 = !{i32 7, !"air.max_constant_buffers", i32 31}
!5 = !{i32 7, !"air.max_threadgroup_buffers", i32 31}
!6 = !{i32 7, !"air.max_textures", i32 128}
!7 = !{i32 7, !"air.max_read_write_textures", i32 8}
!8 = !{i32 7, !"air.max_samplers", i32 16}
!20 = !{!"air.compile.denorms_disable"}
!21 = !{!"air.compile.fast_math_enable"}
!22 = !{!"hand-written AIR for layerprobe (spes): bg_vs / bg_fs_color of iOSPlus10 probes/layerprobe.metal"}
!23 = !{i32 2, i32 8, i32 0}
!24 = !{!"Metal", i32 4, i32 0, i32 0}
!air.vertex = !{!9}
!9 = !{ptr @bg_vs, !10, !14}
!10 = !{!11, !12, !13}
!11 = !{!"air.position", !"air.arg_type_name", !"float4", !"air.arg_name", !"pos"}
!12 = !{!"air.vertex_output", !"generated(5colorDv4_f)", !"air.arg_type_name", !"float4", !"air.arg_name", !"color"}
!13 = !{!"air.vertex_output", !"generated(2uvDv2_f)", !"air.arg_type_name", !"float2", !"air.arg_name", !"uv"}
!14 = !{!15, !16}
!15 = !{i32 0, !"air.vertex_id", !"air.arg_type_name", !"uint", !"air.arg_name", !"vid"}
!16 = !{i32 1, !"air.buffer", !"air.location_index", i32 0, i32 1, !"air.read", !"air.address_space", i32 1, !"air.arg_type_size", i32 16, !"air.arg_type_align_size", i32 16, !"air.arg_type_name", !"float4", !"air.arg_name", !"data"}
